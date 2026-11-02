"""Turns a page the user captured in their own browser into stored ad records.

Pipeline: page text -> rule-based segments per ad -> optional local-LLM pass to
fill missing text fields -> grounding check -> dedupe -> SQLite.
"""
import logging

from services.capture.grounding import ground
from services.capture.llm import LLMUnavailable
from services.capture.page_text import clean, html_to_text
from services.capture.rules import is_own_host, is_page_chrome, parse, platform_for_url, search_countries
from services.normalizer import NormalizedAd, dedupe

log = logging.getLogger(__name__)

COVERAGE = ('Captured from your browser: only the ads that were loaded on the captured page(s). Scroll to load more '
            'results and capture again to add them.')
TEXT_FIELDS = ('advertiser_name', 'author', 'headline', 'ad_copy', 'description', 'call_to_action', 'creative_type')
LLM_FILLABLE = ('advertiser_name', 'author', 'headline', 'ad_copy', 'description', 'call_to_action', 'creative_type',
                'landing_page_url', 'first_seen', 'last_seen')


class CaptureError(ValueError):
    pass


def clean_llm_fields(platform, fields, dropped):
    """Grounded values can still be library UI text ("View details", "Single image ad") or the library's own links."""
    for key in TEXT_FIELDS:
        if key in fields and is_page_chrome(platform, key, fields[key]):
            fields.pop(key)
            dropped.append(key)
    if fields.get('landing_page_url') and is_own_host(platform, fields['landing_page_url']):
        fields.pop('landing_page_url')
        dropped.append('landing_page_url')
    if fields.get('headline') and fields.get('headline') == fields.get('ad_copy'):
        fields.pop('headline')
    return fields, dropped


def needs_llm(ad):
    return not ad.advertiser_name or not (ad.ad_copy or ad.headline)


class CaptureService:
    def __init__(self, storage, settings, llm=None):
        self.storage = storage
        self.settings = settings
        self.llm = llm

    async def ingest(self, *, page_url, text=None, html=None, fetch_id, company=None, use_llm=True):
        platform = platform_for_url(page_url)
        if not platform:
            raise CaptureError('Page URL must be an https page on facebook.com, linkedin.com or adstransparency.google.com.')
        page = clean(text) if text else html_to_text(html)
        if not page:
            raise CaptureError('The captured page is empty.')

        warnings = []
        ads = parse(platform, page, page_url, company)
        method = 'rules'
        if use_llm and self.llm:
            try:
                if ads:
                    if await self._enrich(ads):
                        method = 'rules+llm'
                else:
                    ads, method = await self._extract(platform, page, page_url, company), 'llm'
            except LLMUnavailable as exc:
                warnings.append(f'{exc} Saved the rule-based results only.')
        for ad in ads:
            ad.source_metadata['capture'].pop('raw_segment', None)
        ads = dedupe(ads)
        self.storage.save_ads(fetch_id, ads)
        summary = self.storage.record_capture(fetch_id, platform, company, page_url, len(ads), COVERAGE, warnings)
        return {'fetch_id': fetch_id, 'platform': platform, 'captured': len(ads), 'method': method,
                'warnings': warnings, 'status': summary}

    async def _enrich(self, ads):
        """Ask the LLM about segments the rules could not read; fill only empty fields, only with grounded values.

        Returns how many segments were sent to the LLM."""
        todo = [a for a in ads if needs_llm(a)][:self.settings.capture_llm_max_segments]
        for ad in todo:
            source = ad.source_metadata['capture']['raw_segment']
            fields, dropped = clean_llm_fields(ad.platform, *ground(await self.llm.extract_segment(source), source))
            if fields.get('headline') and fields['headline'] == ad.ad_copy:
                fields.pop('headline')
            filled = [k for k in LLM_FILLABLE if fields.get(k) and getattr(ad, k) in (None, '')]
            for key in filled:
                setattr(ad, key, fields[key])
            if 'first_seen' in filled and not ad.date_type:
                ad.date_type = 'first_shown'
            ad.source_metadata['capture'].update(llm_filled=filled, llm_rejected=dropped)
            ad.__post_init__()  # re-validate URLs
        return len(todo)

    async def _extract(self, platform, page, page_url, company):
        """No ad anchors found: let the LLM propose ads from the page, keeping only grounded, identifiable ones."""
        ads = []
        for item in await self.llm.extract_page(page):
            fields, dropped = clean_llm_fields(platform, *ground(item['candidate'], item['source']))
            if not (fields.get('ad_id') or (fields.get('advertiser_name') and (fields.get('headline') or fields.get('ad_copy')))):
                continue
            ad_id = fields.pop('ad_id', None)
            ad_url = f'https://www.facebook.com/ads/library/?id={ad_id}' if platform == 'meta' and ad_id and ad_id.isdigit() else None
            ads.append(NormalizedAd(
                platform=platform, ad_id=ad_id, company_name=company, ad_url=ad_url, country=search_countries(page_url),
                date_type='first_shown' if fields.get('first_seen') else None, source_type='user_capture',
                source_metadata={'capture': {'page_url': page_url, 'method': 'llm', 'llm_rejected': dropped,
                                             'segment_text': item['source'][:4000]}},
                **fields))
        return ads
