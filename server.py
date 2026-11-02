"""Public Ads Explorer API (FastAPI).

Run:  python server.py   ->  http://127.0.0.1:8765
"""
from datetime import date
import csv
import io
import json
import os
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from adapters import build_registry
from adapters.base import FetchRequest
from config import ROOT, settings as default_settings
from database.storage import Storage
from services.ad_fetcher import AdFetcher
from services.capture.llm import OllamaExtractor
from services.capture.service import CaptureError, CaptureService
from services.validation import PLATFORMS, normalize_domain

DIST = ROOT / 'frontend' / 'dist'

EXPORT_FIELDS = [
    'platform', 'ad_id', 'advertiser_name', 'author', 'headline', 'ad_copy', 'description', 'creative_type',
    'call_to_action', 'ad_url', 'landing_page_url', 'creative_url', 'published_date', 'date_type', 'first_seen',
    'last_seen', 'country', 'ad_status', 'source_type', 'retrieved_at',
]


class FetchBody(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=255)
    platforms: list[str] = Field(min_length=1, max_length=len(PLATFORMS))
    country: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    start_date: date | None = None
    end_date: date | None = None
    limit_per_platform: int = Field(default=100, ge=1, le=500)
    fetch_id: str | None = Field(default=None, pattern=r'^[0-9a-fA-F-]{8,40}$')
    meta_page_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator('company')
    @classmethod
    def strip_company(cls, v):
        v = ' '.join(v.split())
        if not v:
            raise ValueError('Company name is required')
        return v

    @field_validator('platforms')
    @classmethod
    def known_platforms(cls, v):
        unknown = sorted(set(v) - set(PLATFORMS))
        if unknown:
            raise ValueError(f'Unknown platforms: {", ".join(unknown)}')
        return list(dict.fromkeys(v))

    @field_validator('domain')
    @classmethod
    def valid_domain(cls, v):
        return normalize_domain(v) if v else None

    @field_validator('meta_page_ids')
    @classmethod
    def numeric_ids(cls, v):
        v = [x.strip() for x in v if x.strip()]
        if any(not x.isdigit() for x in v):
            raise ValueError('Meta Page IDs must be numeric')
        return v

    @model_validator(mode='after')
    def date_order(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('start_date must be on or before end_date')
        return self


class CaptureBody(BaseModel):
    page_url: str = Field(min_length=8, max_length=2048)
    text: str | None = None
    html: str | None = None
    fetch_id: str | None = Field(default=None, pattern=r'^[0-9a-fA-F-]{8,40}$')
    company: str | None = Field(default=None, max_length=120)
    use_llm: bool = True

    @model_validator(mode='after')
    def has_content(self):
        if not (self.text or self.html):
            raise ValueError('Provide the page text or HTML')
        return self


def csv_safe(value):
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def create_app(registry=None, storage=None, settings=None, llm=None):
    settings = settings or default_settings
    registry = registry or build_registry()
    storage = storage or Storage(settings.db_path)
    fetcher = AdFetcher(registry, storage, settings)
    llm = llm or OllamaExtractor(settings.ollama_url, settings.ollama_model)
    capture = CaptureService(storage, settings, llm)
    app = FastAPI(title='Public Ads Explorer', version='2.0')
    app.state.storage = storage
    app.state.registry = registry

    @app.middleware('http')
    async def headers(request: Request, call_next):
        if request.url.path.startswith('/api/'):
            limit = settings.capture_max_bytes if request.url.path == '/api/capture' else 16_384
            if int(request.headers.get('content-length') or 0) > limit:
                return JSONResponse({'detail': 'Request body too large'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/ads/fetch')
    async def fetch_ads(body: FetchBody):
        fetch_id = body.fetch_id or str(uuid.uuid4())
        req = FetchRequest(company_name=body.company, company_domain=body.domain, country=body.country,
                           start_date=body.start_date, end_date=body.end_date, limit=body.limit_per_platform,
                           meta_page_ids=body.meta_page_ids)
        platforms = await fetcher.fetch(fetch_id, req, body.platforms)
        total, ads = storage.query_ads({'fetch_id': fetch_id}, page_size=None)
        return {'fetch_id': fetch_id, 'total': total, 'ads': ads, 'platforms': platforms}

    def filters(fetch_id, platform, q, date_from, date_to, sort, order):
        return {'fetch_id': fetch_id, 'platforms': [p for p in platform if p in PLATFORMS], 'q': (q or '').strip()[:100],
                'date_from': date_from, 'date_to': date_to, 'sort': sort, 'order': order}

    @app.get('/api/ads')
    def list_ads(fetch_id: str | None = None, platform: list[str] = Query(default=[]), q: str | None = None,
                 date_from: date | None = None, date_to: date | None = None, sort: str = 'platform',
                 order: str = 'asc', page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
        total, ads = storage.query_ads(filters(fetch_id, platform, q, date_from, date_to, sort, order), page, page_size)
        return {'total': total, 'page': page, 'page_size': page_size, 'ads': ads}

    @app.get('/api/ads/export')
    def export_ads(format: str = Query('csv', pattern='^(csv|json)$'), fetch_id: str | None = None,
                   platform: list[str] = Query(default=[]), q: str | None = None, date_from: date | None = None,
                   date_to: date | None = None, sort: str = 'platform', order: str = 'asc'):
        _, ads = storage.query_ads(filters(fetch_id, platform, q, date_from, date_to, sort, order), page_size=None)
        if format == 'json':
            body = json.dumps([{k: v for k, v in a.items() if k != 'row'} for a in ads], ensure_ascii=False, indent=2)
            return Response(body, media_type='application/json',
                            headers={'Content-Disposition': 'attachment; filename="public-ads.json"'})
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['S.No.', 'Ad Platform', 'Details', 'URL', 'Published Date', 'Author', *EXPORT_FIELDS])
        for i, ad in enumerate(ads, 1):
            row = ad['row']
            details = ' — '.join(x for x in (ad.get('headline'), ad.get('ad_copy') or ad.get('description')) if x) or row['headline']
            writer.writerow([i, row['platform'], csv_safe(details), row['url_label'], row['published_date'], csv_safe(row['author']),
                             *(csv_safe(ad.get(f)) for f in EXPORT_FIELDS)])
        return Response('﻿' + out.getvalue(), media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="public-ads.csv"'})

    @app.get('/api/ads/{ad_pk}')
    def get_ad(ad_pk: int):
        ad = storage.get_ad(ad_pk)
        if not ad:
            raise HTTPException(404, 'Ad not found')
        return ad

    @app.get('/api/platforms/status')
    def platform_status(fetch_id: str | None = None):
        last = storage.statuses(fetch_id)
        return {'platforms': [{**a.capability(), 'last': last.get(p)} for p, a in registry.items()]}

    @app.post('/api/capture')
    async def capture_page(body: CaptureBody, request: Request):
        # JSON only: a cross-site form post cannot reach this without a CORS preflight, which is never granted.
        if not request.headers.get('content-type', '').startswith('application/json'):
            raise HTTPException(415, 'Content-Type must be application/json')
        company = ' '.join((body.company or '').split()) or None
        try:
            return await capture.ingest(page_url=body.page_url, text=body.text, html=body.html,
                                        fetch_id=body.fetch_id or str(uuid.uuid4()), company=company,
                                        use_llm=body.use_llm)
        except CaptureError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/llm/status')
    async def llm_status():
        return await llm.status()

    @app.get('/capture.html', include_in_schema=False)
    def capture_html():
        page = DIST / 'capture.html'
        if page.is_file():
            return FileResponse(page)
        raise HTTPException(404, 'Frontend not built')

    if (DIST / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    @app.get('/', include_in_schema=False)
    def index():
        page = DIST / 'index.html'
        if page.is_file():
            return FileResponse(page)
        return Response('Frontend not built. Run `npm install && npm run build` in frontend/, '
                        'or use the dev server (npm run dev).', media_type='text/plain')

    return app


app = None if os.getenv('PUBLIC_ADS_NO_APP') else create_app()


def main():
    import uvicorn

    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('PORT', '8765')))


if __name__ == '__main__':
    main()
