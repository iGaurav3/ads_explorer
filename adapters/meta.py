"""Meta Ad Library API connector (official, free; needs a developer access token).

Docs: https://developers.facebook.com/docs/graph-api/reference/ads_archive/
      https://developers.facebook.com/docs/graph-api/reference/archived-ad/
Non-political ads are only returned when they reached the EU/UK.
`ad_snapshot_url` is deliberately not requested: it embeds the access token.
"""
import asyncio
import json
from datetime import date

from adapters.base import AdapterError, BaseAdapter, FetchRequest, now_iso
from config import settings
from services.http_client import HttpError, NetworkError, get_json, new_client
from services.normalizer import NormalizedAd, dedupe
from services.validation import host_matches, name_matches, redact

HOSTS = frozenset({'graph.facebook.com'})
MAX_PAGES = 20
FIELDS = ','.join((
    'id', 'ad_creation_time', 'ad_creative_bodies', 'ad_creative_link_captions', 'ad_creative_link_descriptions',
    'ad_creative_link_titles', 'ad_delivery_start_time', 'ad_delivery_stop_time', 'page_id', 'page_name',
    'publisher_platforms', 'languages', 'eu_total_reach', 'beneficiary_payers', 'total_reach_by_location',
))
AUTH_CODES = {102, 190, 10, 200, 2332}
RATE_CODES = {4, 17, 32, 613, 80004}


def first(values):
    if isinstance(values, list):
        return next((str(v) for v in values if v), None)
    return values or None


def payer(row):
    for item in row.get('beneficiary_payers') or []:
        if isinstance(item, dict) and item.get('payer'):
            return item['payer']
    return None


def normalize(row, company, today=None):
    ad_id = str(row['id']) if row.get('id') else None
    stop = row.get('ad_delivery_stop_time')
    status = 'unknown'
    if stop and stop[:10] < (today or date.today()).isoformat():
        status = 'inactive'
    metadata = {k: v for k, v in {
        'page_id': row.get('page_id'), 'publisher_platforms': row.get('publisher_platforms'),
        'languages': row.get('languages'), 'eu_total_reach': row.get('eu_total_reach'),
        'beneficiary_payers': row.get('beneficiary_payers'), 'total_reach_by_location': row.get('total_reach_by_location'),
        'ad_creation_time': row.get('ad_creation_time'), 'link_caption': first(row.get('ad_creative_link_captions')),
        'all_bodies': row.get('ad_creative_bodies') if len(row.get('ad_creative_bodies') or []) > 1 else None,
        'all_titles': row.get('ad_creative_link_titles') if len(row.get('ad_creative_link_titles') or []) > 1 else None,
    }.items() if v not in (None, '', [])}
    return NormalizedAd(
        platform='meta',
        ad_id=ad_id,
        company_name=company,
        advertiser_name=row.get('page_name'),
        headline=first(row.get('ad_creative_link_titles')),
        description=first(row.get('ad_creative_link_descriptions')),
        ad_copy=first(row.get('ad_creative_bodies')),
        ad_url=f'https://www.facebook.com/ads/library/?id={ad_id}' if ad_id and ad_id.isdigit() else None,
        date_type='delivery_start' if row.get('ad_delivery_start_time') else None,
        first_seen=row.get('ad_delivery_start_time'),
        last_seen=stop,
        author=payer(row) or row.get('page_name'),
        ad_status=status,
        source_type='official_api',
        source_metadata=metadata,
    )


class MetaAdapter(BaseAdapter):
    platform = 'meta'
    display_name = 'Meta (Facebook & Instagram)'
    coverage = ('Meta Ad Library API: all ads that reached the EU/UK; elsewhere only social-issue, '
                'electoral and political ads.')
    requires_credentials = True

    def __init__(self, client_factory=None, sleep=asyncio.sleep):
        self.client_factory = client_factory or (lambda: new_client(settings.http_timeout))
        self.sleep = sleep

    def is_configured(self):
        return bool(settings.meta_access_token)

    def setup_hint(self):
        return ('No token needed: open the Meta Ad Library below, then click "Send to Ads Explorer" (Capture from '
                'browser). Optional: set META_ACCESS_TOKEN for automatic fetching via the official API.')

    def fallback_url(self, req):
        from urllib.parse import urlencode
        return 'https://www.facebook.com/ads/library/?' + urlencode({
            'active_status': 'all', 'ad_type': 'all', 'country': req.country or 'ALL',
            'q': req.company_name, 'search_type': 'keyword_unordered', 'media_type': 'all'})

    def _params(self, req):
        params = {
            'ad_type': 'ALL', 'ad_active_status': 'ALL', 'fields': FIELDS,
            'ad_reached_countries': json.dumps([req.country or 'ALL']),
            'limit': min(100, req.limit),
        }
        if req.meta_page_ids:
            params['search_page_ids'] = json.dumps(req.meta_page_ids[:10])
        else:
            params['search_terms'] = req.company_name[:100]
            params['search_type'] = 'KEYWORD_UNORDERED'
        if req.start_date:
            params['ad_delivery_date_min'] = req.start_date.isoformat()
        if req.end_date:
            params['ad_delivery_date_max'] = req.end_date.isoformat()
        return params

    async def _get(self, client, params):
        url = f'https://graph.facebook.com/{settings.meta_api_version}/ads_archive'
        try:
            return await get_json(client, url, params=params, allowed_hosts=HOSTS, sleep=self.sleep,
                                  headers={'Authorization': f'Bearer {settings.meta_access_token}'})
        except HttpError as exc:
            err = (exc.payload or {}).get('error', {}) if isinstance(exc.payload, dict) else {}
            code = err.get('code')
            message = redact(err.get('message') or str(exc), settings.secrets())
            if code in AUTH_CODES or exc.status_code == 401:
                raise AdapterError('access_required', f'Meta rejected the access token or its permissions: {message}')
            if code in RATE_CODES or exc.status_code == 429:
                raise AdapterError('rate_limited', f'Meta API rate limit reached: {message}')
            raise AdapterError('error', f'Meta API error {code or exc.status_code}: {message}')
        except NetworkError as exc:
            raise AdapterError('error', redact(exc, settings.secrets()))

    async def fetch_ads(self, req: FetchRequest):
        started = now_iso()
        if not self.is_configured():
            return self.result(req, 'access_required', setup_hint=self.setup_hint(), started_at=started, finished_at=now_iso(),
                               error='Meta Ad Library API needs a free access token; none is configured.')
        warnings, rows, partial = [], [], False
        params = self._params(req)
        try:
            async with self.client_factory() as client:
                for _ in range(MAX_PAGES):
                    try:
                        payload = await self._get(client, params)
                    except AdapterError:
                        if not rows:
                            raise
                        partial = True
                        break
                    data = [r for r in (payload or {}).get('data', []) if isinstance(r, dict)]
                    if not data:
                        break
                    rows.extend(data)
                    after = ((payload.get('paging') or {}).get('cursors') or {}).get('after')
                    if len(rows) >= req.limit * 3 or not after or not (payload.get('paging') or {}).get('next'):
                        break
                    params = {**params, 'after': after}
        except AdapterError as exc:
            return self.result(req, exc.status, error=exc.message, started_at=started, finished_at=now_iso(),
                               setup_hint=self.setup_hint() if exc.status == 'access_required' else None)

        ads = dedupe(normalize(r, req.company_name) for r in rows)
        if not req.meta_page_ids:
            # Keyword search also returns ads that merely mention the company; keep the advertiser's own pages.
            kept = [a for a in ads if name_matches(a.advertiser_name, req.company_name)
                    or (req.company_domain and host_matches(a.source_metadata.get('link_caption'), req.company_domain))]
            if len(kept) != len(ads):
                warnings.append(f'{len(ads) - len(kept)} ad(s) from other Pages that only mention "{req.company_name}" were excluded. '
                                'Use a Meta Page ID for an exact advertiser search.')
            ads = kept
        ads = ads[:req.limit]
        if not req.country:
            warnings.append('No country selected: non-political results only include ads that reached the EU/UK.')
        status = ('partial_results' if ads else 'error') if partial else ('success' if ads else 'no_results')
        return self.result(req, status, ads, warnings=warnings, started_at=started, finished_at=now_iso(),
                           error='Meta paging stopped early; results are incomplete.' if partial else None)
