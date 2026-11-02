"""Microsoft Advertising Ad Library API connector (official, unauthenticated).

Docs: https://learn.microsoft.com/en-us/advertising/guides/ad-library-api
- GET Advertisers?searchText&top&skip
- GET Ads?advertiserId|searchText&top&skip&startDate&endDate&countryCodes
- GET Ads/{AdId}?$expand=AdDetails   (AdDetails only available for a single Ad)
Coverage: ads served in the EU/EEA only (since June 2023).
"""
import asyncio
from urllib.parse import quote

from adapters.base import AdapterError, BaseAdapter, FetchRequest, now_iso
from config import settings
from services.http_client import HttpError, NetworkError, get_json, new_client
from services.normalizer import NormalizedAd, dedupe
from services.validation import host_matches, match_rank

BASE = 'https://adlibrary.api.bingads.microsoft.com/api/v1/'
HOSTS = frozenset({'adlibrary.api.bingads.microsoft.com'})
PAGE_SIZE = 24  # the unauthenticated API rejects top > 24 (verified live, 2026-10-27)
MAX_PAGES = 30
DETAIL_CONCURRENCY = 3

# ISO-3166 alpha-2 -> Ad Library Country value set (from the official docs)
COUNTRY_CODES = {
    'AT': 10, 'BE': 14, 'BG': 26, 'HR': 49, 'CY': 207, 'CZ': 51, 'DK': 53, 'EE': 61, 'FI': 65,
    'FR': 66, 'DE': 72, 'GR': 76, 'HU': 88, 'IE': 92, 'IT': 93, 'LV': 104, 'LT': 108, 'LU': 109,
    'MT': 115, 'NL': 129, 'PL': 151, 'PT': 152, 'RO': 226, 'SK': 165, 'SI': 167, 'ES': 170,
    'SE': 175, 'IS': 89, 'LI': 107, 'NO': 139,
}


def items(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for name in ('value', 'Value', 'items', 'Items'):
            if isinstance(payload.get(name), list):
                return [x for x in payload[name] if isinstance(x, dict)]
    return []


def lower_keys(row):
    return {str(k).lower(): v for k, v in (row or {}).items()} if isinstance(row, dict) else {}


def normalize(row, company):
    r = lower_keys(row)
    d = lower_keys(r.get('addetails'))
    metadata = {k: v for k, v in {
        'AdvertiserId': r.get('advertiserid'), 'DisplayUrl': r.get('displayurl'), 'AssetJson': r.get('assetjson'),
        'TotalImpressionsRange': d.get('totalimpressionsrange'), 'ImpressionsByCountry': d.get('impressionsbycountry'),
        'Targets': d.get('targets'), 'RestrictionReason': d.get('restrictionreason'), 'PaidForByName': d.get('paidforbyname'),
    }.items() if v not in (None, '', [])}
    return NormalizedAd(
        platform='microsoft',
        ad_id=str(r['adid']) if r.get('adid') is not None else None,
        company_name=company,
        advertiser_name=r.get('advertisername'),
        headline=r.get('title'),
        description=r.get('description'),
        ad_copy=r.get('description'),
        landing_page_url=r.get('destinationurl'),
        ad_url=None,  # The API exposes no verified per-ad public URL.
        date_type='first_served' if d.get('startdate') else None,
        first_seen=d.get('startdate'),
        last_seen=d.get('enddate'),
        author=d.get('paidforbyname') or r.get('advertisername'),
        source_type='official_api',
        source_metadata=metadata,
    )


class MicrosoftAdapter(BaseAdapter):
    platform = 'microsoft'
    display_name = 'Microsoft / Bing Ads'
    coverage = 'Microsoft Ad Library: ads served in the EU/EEA only (since June 2023).'

    def __init__(self, client_factory=None, sleep=asyncio.sleep):
        self.client_factory = client_factory or (lambda: new_client(settings.microsoft_timeout))
        self.sleep = sleep

    def fallback_url(self, req):
        return 'https://adlibrary.ads.microsoft.com/'

    async def _get(self, client, path, params=None):
        try:
            return await get_json(client, BASE + path, params=params, allowed_hosts=HOSTS, sleep=self.sleep, retries=1)
        except HttpError as exc:
            if exc.status_code == 429:
                raise AdapterError('rate_limited', 'Microsoft unauthenticated rate limit reached; try again later.')
            if exc.status_code in (401, 403):
                raise AdapterError('blocked', f'Microsoft Ad Library refused the request ({exc}).')
            detail = ((exc.payload or {}).get('error') or {}).get('message', '') if isinstance(exc.payload, dict) else ''
            raise AdapterError('error', f'Microsoft Ad Library error ({exc}). {detail[:160]}'.strip())
        except NetworkError as exc:
            raise AdapterError('error', f'Microsoft Ad Library did not respond in time ({exc}). The public API can be slow; try again.')

    async def fetch_ads(self, req: FetchRequest):
        started = now_iso()
        warnings = []
        filters = {}
        if req.start_date:
            filters['startDate'] = req.start_date.isoformat()
        if req.end_date:
            filters['endDate'] = req.end_date.isoformat()
        if req.country:
            if req.country in COUNTRY_CODES:
                filters['countryCodes'] = str(COUNTRY_CODES[req.country])
            else:
                return self.result(req, 'no_results', started_at=started, finished_at=now_iso(),
                                   warnings=[f'{req.country} is outside the EU/EEA; Microsoft only publishes EU/EEA ads.'])
        try:
            async with self.client_factory() as client:
                advertisers = items(await self._get(client, 'Advertisers', {'searchText': req.company_name[:100], 'top': PAGE_SIZE, 'skip': 0}))
                ranked = sorted(
                    ((match_rank(lower_keys(a).get('advertisername'), req.company_name), lower_keys(a)) for a in advertisers),
                    key=lambda x: x[0])
                candidates = [a for rank, a in ranked if rank < 9 and a.get('advertiserid') is not None][:3]

                rows, partial = [], False
                if candidates:
                    for advertiser in candidates:
                        got, failed = await self._list_ads(client, {'advertiserId': advertiser['advertiserid'], **filters}, req.limit - len(rows))
                        rows.extend(got)
                        partial = partial or failed
                        if len(rows) >= req.limit:
                            break
                else:
                    warnings.append('No advertiser matched the name; results come from an ad-copy search, so advertiser identity is not confirmed.')
                    rows, partial = await self._list_ads(client, {'searchText': req.company_name[:100], **filters}, req.limit)

                ads = dedupe(normalize(r, req.company_name) for r in rows)
                if req.company_domain:
                    before = len(ads)
                    ads = [a for a in ads if host_matches(a.landing_page_url, req.company_domain)
                           or host_matches(a.source_metadata.get('DisplayUrl'), req.company_domain)]
                    if before != len(ads):
                        warnings.append(f'{before - len(ads)} ad(s) dropped because their URLs do not match {req.company_domain}.')
                ads = ads[:req.limit]
                detail_failures = await self._expand_details(client, ads, warnings)
        except AdapterError as exc:
            return self.result(req, exc.status, error=exc.message, started_at=started, finished_at=now_iso())

        if partial or detail_failures:
            status = 'partial_results' if ads else 'error'
        else:
            status = 'success' if ads else 'no_results'
        return self.result(req, status, ads, warnings=warnings, started_at=started, finished_at=now_iso(),
                           error='Some Microsoft requests failed; results are incomplete.' if status in ('partial_results', 'error') else None)

    async def _list_ads(self, client, params, wanted):
        """Page through Ads until `wanted` ads, an empty page or MAX_PAGES. Returns (rows, partial)."""
        rows, skip = [], 0
        for _ in range(MAX_PAGES):
            if len(rows) >= wanted:
                break
            try:
                page = items(await self._get(client, 'Ads', {**params, 'top': min(PAGE_SIZE, wanted - len(rows)), 'skip': skip}))
            except AdapterError:
                if not rows:
                    raise
                return rows, True
            if not page:
                break
            rows.extend(page)
            skip += len(page)
        return rows[:wanted], False

    async def _expand_details(self, client, ads, warnings):
        """Fill dates/payer from Ads/{id}?$expand=AdDetails, with bounded concurrency."""
        targets = [a for a in ads if a.ad_id][:settings.microsoft_max_details]
        if len(targets) < len(ads):
            warnings.append(f'Ad details (dates, payer) fetched for the first {len(targets)} ads only, to respect unauthenticated rate limits.')
        semaphore = asyncio.Semaphore(DETAIL_CONCURRENCY)
        failures = 0

        async def expand(ad):
            nonlocal failures
            async with semaphore:
                try:
                    payload = await self._get(client, f'Ads/{quote(ad.ad_id)}', {'$expand': 'AdDetails'})
                except AdapterError:
                    failures += 1
                    return
            row = payload[0] if isinstance(payload, list) and payload else payload
            detailed = normalize(row if isinstance(row, dict) else {}, ad.company_name)
            for name in ('first_seen', 'last_seen', 'date_type', 'author'):
                if getattr(detailed, name):
                    setattr(ad, name, getattr(detailed, name))
            ad.source_metadata.update(detailed.source_metadata)

        await asyncio.gather(*(expand(a) for a in targets))
        if failures:
            warnings.append(f'Details could not be loaded for {failures} ad(s).')
        return failures
