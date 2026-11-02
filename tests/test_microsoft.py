import asyncio
from datetime import date

import httpx

from adapters.base import FetchRequest
from adapters.microsoft import MicrosoftAdapter
from config import settings
from tests.conftest import mock_factory, no_sleep
from tests.fixtures.microsoft import responses as fx


def handler_factory(calls, fail_details=False, rate_limit=False):
    def handler(request: httpx.Request):
        calls.append(request)
        path = request.url.path.removeprefix('/api/v1/')
        params = dict(request.url.params)
        if rate_limit:
            return httpx.Response(429, json={})
        if path == 'Advertisers':
            return httpx.Response(200, json=fx.ADVERTISERS)
        if path == 'Ads':
            skip = int(params.get('skip', 0))
            page = {0: fx.ADS_PAGE_1, 2: fx.ADS_PAGE_2}.get(skip, [])
            return httpx.Response(200, json={'value': page})
        if path.startswith('Ads/'):
            if fail_details:
                return httpx.Response(500, json={})
            return httpx.Response(200, json=fx.DETAILS[int(path.split('/')[1])])
        return httpx.Response(404)
    return handler


def run(req, **kw):
    calls = []
    adapter = MicrosoftAdapter(client_factory=mock_factory(handler_factory(calls, **kw)), sleep=no_sleep)
    return asyncio.run(adapter.fetch_ads(req)), calls


def test_parses_documented_structures_and_paginates():
    result, calls = run(FetchRequest('Fixture Shoes', limit=10))
    assert result.status == 'success'
    assert [a.ad_id for a in result.ads] == ['501', '502', '503']  # duplicate 501 removed
    ads_calls = [c for c in calls if c.url.path.endswith('/Ads')]
    assert all(c.url.params['advertiserId'] == '1001' for c in ads_calls)  # Unrelated Corp not queried
    first = result.ads[0]
    assert first.headline == 'Fixture title A'
    assert first.landing_page_url == 'https://www.fixtureshoes.example/a'
    assert first.source_metadata['DisplayUrl'] == 'fixtureshoes.example'
    assert first.ad_url is None  # no verified per-ad URL; never the homepage


def test_detail_expansion_maps_dates_and_payer():
    result, calls = run(FetchRequest('Fixture Shoes', limit=10))
    by_id = {a.ad_id: a for a in result.ads}
    assert any(c.url.params.get('$expand') == 'AdDetails' for c in calls)
    assert by_id['501'].first_seen.startswith('2024-02-01')
    assert by_id['501'].date_type == 'first_served'
    assert by_id['501'].published_date is None
    assert by_id['501'].author == 'Fixture Payer Ltd'          # payer disclosed
    assert by_id['502'].author == 'Fixture Shoes GmbH'         # falls back to advertiser
    assert by_id['503'].first_seen is None and by_id['503'].date_type is None


def test_filters_are_sent_and_country_mapped():
    _, calls = run(FetchRequest('Fixture Shoes', country='DE', start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)))
    ads_call = next(c for c in calls if c.url.path.endswith('/Ads'))
    assert ads_call.url.params['countryCodes'] == '72'
    assert ads_call.url.params['startDate'] == '2024-01-01'
    assert ads_call.url.params['endDate'] == '2024-06-30'


def test_non_eea_country_is_explained_without_calls():
    result, calls = run(FetchRequest('Fixture Shoes', country='US'))
    assert result.status == 'no_results' and not calls and 'EU/EEA' in result.warnings[0]


def test_domain_filter():
    result, _ = run(FetchRequest('Fixture Shoes', company_domain='fixtureshoes.example'))
    assert [a.ad_id for a in result.ads] == ['501', '502']


def test_failed_details_give_partial_results():
    result, _ = run(FetchRequest('Fixture Shoes', limit=10), fail_details=True)
    assert result.status == 'partial_results' and len(result.ads) == 3


def test_rate_limit_status_not_no_results():
    result, _ = run(FetchRequest('Fixture Shoes'), rate_limit=True)
    assert result.status == 'rate_limited' and not result.ads


def test_detail_cap(monkeypatch):
    monkeypatch.setattr(settings, 'microsoft_max_details', 1)
    result, calls = run(FetchRequest('Fixture Shoes', limit=10))
    assert sum(1 for c in calls if '/Ads/' in c.url.path) == 1
    assert any('first 1 ads' in w for w in result.warnings)
