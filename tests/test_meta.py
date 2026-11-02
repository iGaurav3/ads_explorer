import asyncio
import json

import httpx
import pytest

from adapters.base import FetchRequest
from adapters.meta import MetaAdapter
from config import settings
from tests.conftest import mock_factory, no_sleep
from tests.fixtures.meta import responses as fx

TOKEN = 'SECRET-TOKEN-123'


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr(settings, 'meta_access_token', TOKEN)


def run(req, handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    return asyncio.run(MetaAdapter(client_factory=mock_factory(wrapped), sleep=no_sleep).fetch_ads(req)), calls


def paged(request):
    return httpx.Response(200, json=fx.PAGE_2 if request.url.params.get('after') == 'a1' else fx.PAGE_1)


def test_without_token_returns_access_required_and_no_calls(monkeypatch):
    monkeypatch.setattr(settings, 'meta_access_token', None)
    result, calls = run(FetchRequest('Fixture Shoes'), paged)
    assert result.status == 'access_required' and not calls and 'META_ACCESS_TOKEN' in result.setup_hint
    assert result.fallback_url.startswith('https://www.facebook.com/ads/library/')


def test_pages_maps_and_filters_mentions():
    result, calls = run(FetchRequest('Fixture Shoes', limit=10), paged)
    assert result.status == 'success'
    assert [a.ad_id for a in result.ads] == ['9001', '9003']   # blog page excluded, duplicate removed
    assert len(calls) == 2
    ad = result.ads[0]
    assert ad.headline == 'Fixture link title' and ad.ad_copy == 'Fixture body one'
    assert ad.advertiser_name == 'Fixture Shoes'
    assert ad.author == 'Fixture Shoes Payer BV'
    assert ad.ad_url == 'https://www.facebook.com/ads/library/?id=9001'
    assert ad.first_seen == '2024-04-01' and ad.date_type == 'delivery_start' and ad.published_date is None
    assert ad.ad_status == 'inactive'
    assert ad.source_metadata['publisher_platforms'] == ['facebook', 'instagram']
    assert result.ads[1].author == 'Fixture Shoes'               # no payer -> page name
    assert any('excluded' in w for w in result.warnings)


def test_request_parameters_and_token_in_header_only():
    _, calls = run(FetchRequest('Fixture Shoes', country='DE'), paged)
    p = calls[0].url.params
    assert p['ad_type'] == 'ALL' and p['ad_active_status'] == 'ALL'
    assert json.loads(p['ad_reached_countries']) == ['DE']
    assert p['search_terms'] == 'Fixture Shoes'
    assert 'ad_snapshot_url' not in p['fields']
    assert TOKEN not in str(calls[0].url)
    assert calls[0].headers['authorization'] == f'Bearer {TOKEN}'


def test_page_ids_mode_keeps_all_results():
    result, calls = run(FetchRequest('Fixture Shoes', meta_page_ids=['77']), paged)
    assert json.loads(calls[0].url.params['search_page_ids']) == ['77']
    assert 'search_terms' not in calls[0].url.params
    assert len(result.ads) == 3


def test_invalid_token_is_access_required_redacted_and_not_retried():
    result, calls = run(FetchRequest('Fixture Shoes'), lambda r: httpx.Response(400, json=fx.TOKEN_ERROR))
    assert result.status == 'access_required' and len(calls) == 1
    assert TOKEN not in json.dumps(result.summary())


def test_rate_limit():
    result, _ = run(FetchRequest('Fixture Shoes'), lambda r: httpx.Response(400, json=fx.RATE_ERROR))
    assert result.status == 'rate_limited'


def test_empty_valid_search_is_no_results():
    result, _ = run(FetchRequest('Fixture Shoes'), lambda r: httpx.Response(200, json={'data': []}))
    assert result.status == 'no_results'
