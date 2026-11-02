"""Google Ads Transparency Center connector using Google's official public dataset.

Dataset: bigquery-public-data.google_ads_transparency_center.creative_stats
Field reference: https://storage.googleapis.com/ads-transparency-center/api-data/README.txt
Coverage: ads served in the EEA and Turkey (first_shown is floored at 2023-03-01).

The same data is offered as a free JSON download, but it is ~170 GB and
refreshed daily, so per-search access goes through BigQuery (free sandbox,
needs a Google account + project). Without that, the connector reports
access_required and offers the public Transparency Center as a fallback link.
The Transparency Center website's internal RPC endpoints are never called.
"""
import asyncio
from urllib.parse import urlencode

from adapters.base import BaseAdapter, FetchRequest, now_iso
from config import settings
from services.normalizer import NormalizedAd, dedupe
from services.validation import match_rank, safe_url

TABLE = '`bigquery-public-data.google_ads_transparency_center.creative_stats`'

ADVERTISER_SQL = f"""
SELECT advertiser_id, ANY_VALUE(advertiser_disclosed_name) AS name, COUNT(*) AS creatives
FROM {TABLE}
WHERE LOWER(advertiser_disclosed_name) LIKE @pattern
GROUP BY advertiser_id
ORDER BY creatives DESC
LIMIT 25
"""

CREATIVE_SQL = f"""
SELECT advertiser_id, advertiser_disclosed_name, advertiser_legal_name, advertiser_location,
       advertiser_verification_status, creative_id, creative_page_url, ad_format_type, topic,
       ad_funded_by, is_funded_by_google_ad_grants,
       ARRAY(SELECT AS STRUCT r.region_code, r.first_shown, r.last_shown,
                    r.times_shown_lower_bound, r.times_shown_upper_bound
             FROM UNNEST(region_stats) r
             WHERE (@country IS NULL OR r.region_code = @country)) AS regions
FROM {TABLE}
WHERE advertiser_id IN UNNEST(@advertiser_ids)
  AND EXISTS (SELECT 1 FROM UNNEST(region_stats) r
              WHERE (@country IS NULL OR r.region_code = @country)
                AND (@start IS NULL OR r.last_shown >= @start)
                AND (@end IS NULL OR r.first_shown <= @end))
LIMIT @limit
"""


class QueryTooLarge(Exception):
    pass


def _str_date(value):
    return value.isoformat() if hasattr(value, 'isoformat') else (str(value) if value else None)


def normalize(row, company):
    regions = [dict(r) for r in (row.get('regions') or [])]
    firsts = [_str_date(r.get('first_shown')) for r in regions if r.get('first_shown')]
    lasts = [_str_date(r.get('last_shown')) for r in regions if r.get('last_shown')]
    page = safe_url(row.get('creative_page_url'))
    if page and not page.startswith('https://adstransparency.google.com/'):
        page = None
    fmt = row.get('ad_format_type')
    return NormalizedAd(
        platform='google',
        ad_id=row.get('creative_id'),
        company_name=company,
        advertiser_name=row.get('advertiser_disclosed_name'),
        creative_type=str(fmt).lower() if fmt else None,
        ad_url=page,
        date_type='first_shown' if firsts else None,
        first_seen=min(firsts) if firsts else None,
        last_seen=max(lasts) if lasts else None,
        author=row.get('ad_funded_by') or row.get('advertiser_disclosed_name'),
        country=regions[0]['region_code'] if len(regions) == 1 else None,
        source_type='official_public_dataset',
        source_metadata={k: v for k, v in {
            'advertiser_id': row.get('advertiser_id'), 'advertiser_legal_name': row.get('advertiser_legal_name'),
            'advertiser_location': row.get('advertiser_location'),
            'advertiser_verification_status': row.get('advertiser_verification_status'),
            'topic': row.get('topic'), 'is_funded_by_google_ad_grants': row.get('is_funded_by_google_ad_grants'),
            'regions': [{k: _str_date(v) if 'shown' in k and 'bound' not in k else v for k, v in r.items()} for r in regions],
        }.items() if v not in (None, '', [])},
    )


class BigQueryRunner:
    """Thin wrapper around google-cloud-bigquery with a dry-run byte cap."""

    def __init__(self, project, max_bytes):
        from google.cloud import bigquery  # optional dependency

        self.bq = bigquery
        self.client = bigquery.Client(project=project)
        self.max_bytes = max_bytes

    def _params(self, params):
        out = []
        for name, (kind, value) in params.items():
            if kind.startswith('ARRAY<'):
                out.append(self.bq.ArrayQueryParameter(name, kind[6:-1], value))
            else:
                out.append(self.bq.ScalarQueryParameter(name, kind, value))
        return out

    def run(self, sql, params):
        qp = self._params(params)
        dry = self.client.query(sql, job_config=self.bq.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=qp))
        if dry.total_bytes_processed > self.max_bytes:
            raise QueryTooLarge(dry.total_bytes_processed)
        job = self.client.query(sql, job_config=self.bq.QueryJobConfig(maximum_bytes_billed=self.max_bytes, query_parameters=qp))
        return [dict(r.items()) for r in job.result()], dry.total_bytes_processed


class GoogleAdapter(BaseAdapter):
    platform = 'google'
    display_name = 'Google (Search, Display, YouTube)'
    coverage = "Google Ads Transparency Center public dataset: ads served in the EEA and Turkey, since March 2023."
    requires_credentials = True

    def __init__(self, runner_factory=None):
        self.runner_factory = runner_factory

    def _bigquery_available(self):
        try:
            import google.cloud.bigquery  # noqa: F401
        except ImportError:
            return False
        return True

    def is_configured(self):
        if self.runner_factory:
            return True
        return bool(settings.google_cloud_project) and self._bigquery_available()

    def setup_hint(self):
        if not self._bigquery_available():
            return ('No token needed: open the Transparency Center below, then click "Send to Ads Explorer" (Capture '
                    'from browser). Optional: install requirements-google.txt and set GOOGLE_CLOUD_PROJECT for '
                    'automatic EEA data.')
        return ('No token needed: open the Transparency Center below and use Capture from browser. Optional: set '
                'GOOGLE_CLOUD_PROJECT (free BigQuery sandbox) and run `gcloud auth application-default login`.')

    def fallback_url(self, req):
        params = {'region': req.country or 'anywhere'}
        if req.company_domain:
            params['domain'] = req.company_domain
        return 'https://adstransparency.google.com/?' + urlencode(params)

    def _runner(self):
        if self.runner_factory:
            return self.runner_factory()
        return BigQueryRunner(settings.google_cloud_project, settings.google_max_bytes_billed)

    async def fetch_ads(self, req: FetchRequest):
        started = now_iso()
        if not self.is_configured():
            return self.result(req, 'access_required', setup_hint=self.setup_hint(), started_at=started, finished_at=now_iso(),
                               error="Google's official dataset is queried through BigQuery, which is not configured.")
        try:
            ads, warnings = await asyncio.to_thread(self._fetch_sync, req)
        except QueryTooLarge as exc:
            gb = exc.args[0] / 1024**3
            return self.result(req, 'error', started_at=started, finished_at=now_iso(),
                               error=f'Query would scan {gb:.1f} GB, above GOOGLE_MAX_BYTES_BILLED. Raise the limit to allow it.')
        except ImportError:
            return self.result(req, 'access_required', setup_hint=self.setup_hint(), started_at=started, finished_at=now_iso())
        except Exception as exc:  # google.api_core exceptions, auth errors
            name = type(exc).__name__
            status = ('access_required' if name in ('Forbidden', 'Unauthorized', 'DefaultCredentialsError', 'RefreshError')
                      else 'rate_limited' if name in ('TooManyRequests', 'ResourceExhausted') else 'error')
            return self.result(req, status, started_at=started, finished_at=now_iso(), error=f'BigQuery {name}: {str(exc)[:200]}',
                               setup_hint=self.setup_hint() if status == 'access_required' else None)
        if req.company_domain:
            warnings.append("Google's dataset has no landing-page domain; the domain filter was not applied.")
        return self.result(req, 'success' if ads else 'no_results', ads, warnings=warnings, started_at=started, finished_at=now_iso())

    def _fetch_sync(self, req):
        runner = self._runner()
        warnings = []
        pattern = '%' + req.company_name.casefold().replace('\\', '').replace('%', '').replace('_', '\\_') + '%'
        advertisers, scanned = runner.run(ADVERTISER_SQL, {'pattern': ('STRING', pattern)})
        ranked = sorted(advertisers, key=lambda a: (match_rank(a.get('name'), req.company_name), -(a.get('creatives') or 0)))
        ids = [a['advertiser_id'] for a in ranked if match_rank(a.get('name'), req.company_name) < 9][:5]
        if not ids:
            return [], warnings
        if len(ranked) > len(ids):
            warnings.append(f'Matched advertisers: {", ".join(a["name"] for a in ranked[:5] if a.get("name"))}.')
        rows, scanned2 = runner.run(CREATIVE_SQL, {
            'advertiser_ids': ('ARRAY<STRING>', ids),
            'country': ('STRING', req.country),
            'start': ('DATE', req.start_date),
            'end': ('DATE', req.end_date),
            'limit': ('INT64', req.limit),
        })
        warnings.append(f'BigQuery scanned {(scanned + scanned2) / 1024**3:.2f} GB for this search.')
        return dedupe(normalize(r, req.company_name) for r in rows), warnings
