"""Orchestration, API, storage, display and export tests (spec §10 items 1, 2, 7-12)."""
import csv
import io
import json

from fastapi.testclient import TestClient

from adapters import build_registry
from adapters.base import BaseAdapter
from database.storage import Storage
from server import create_app
from services.normalizer import NOT_DISCLOSED, NormalizedAd


class SpyAdapter(BaseAdapter):
    def __init__(self, platform, ads=(), status='success', boom=False):
        self.platform = self.display_name = platform
        self.ads, self.status, self.boom, self.calls = list(ads), status, boom, 0

    async def fetch_ads(self, req):
        self.calls += 1
        if self.boom:
            raise RuntimeError('connector crashed')
        return self.result(req, self.status, [NormalizedAd(**a.to_dict()) for a in self.ads])


def fixture_ad(platform, ad_id, **kw):
    return NormalizedAd(platform=platform, ad_id=ad_id, source_type='test_fixture', **kw)


def make_client(test_settings, adapters):
    registry = {a.platform: a for a in adapters}
    app = create_app(registry=registry, storage=Storage(test_settings.db_path), settings=test_settings)
    return TestClient(app)


def all_spies(**overrides):
    names = ['linkedin', 'meta', 'google', 'microsoft', 'tiktok', 'pinterest', 'snapchat', 'twitter']
    return {n: overrides.get(n, SpyAdapter(n)) for n in names}


def test_only_linkedin_invoked(test_settings):
    spies = all_spies()
    make_client(test_settings, spies.values()).post('/api/ads/fetch', json={'company': 'Acme', 'platforms': ['linkedin']})
    assert {n: s.calls for n, s in spies.items() if s.calls} == {'linkedin': 1}


def test_only_selected_platforms_invoked(test_settings):
    spies = all_spies()
    make_client(test_settings, spies.values()).post('/api/ads/fetch', json={'company': 'Acme', 'platforms': ['meta', 'microsoft']})
    assert {n for n, s in spies.items() if s.calls} == {'meta', 'microsoft'}


def test_unknown_platform_rejected(test_settings):
    r = make_client(test_settings, all_spies().values()).post('/api/ads/fetch', json={'company': 'Acme', 'platforms': ['myspace']})
    assert r.status_code == 422


def test_failures_do_not_discard_other_results(test_settings):
    spies = all_spies(
        microsoft=SpyAdapter('microsoft', [fixture_ad('microsoft', '1', headline='MS ad')]),
        meta=SpyAdapter('meta', boom=True),
        google=SpyAdapter('google', status='blocked'),
    )
    body = make_client(test_settings, spies.values()).post(
        '/api/ads/fetch', json={'company': 'Acme', 'platforms': ['microsoft', 'meta', 'google']}).json()
    assert body['total'] == 1 and body['ads'][0]['headline'] == 'MS ad'
    assert body['platforms']['meta']['status'] == 'error' and 'crashed' in body['platforms']['meta']['error']
    assert body['platforms']['google']['status'] == 'blocked'
    assert body['platforms']['microsoft']['status'] == 'success'


def test_one_row_per_ad_and_not_disclosed(test_settings):
    ads = [fixture_ad('meta', str(i), headline=f'H{i}') for i in range(5)] + [fixture_ad('meta', '99')]
    client = make_client(test_settings, all_spies(meta=SpyAdapter('meta', ads)).values())
    body = client.post('/api/ads/fetch', json={'company': 'Acme', 'platforms': ['meta']}).json()
    assert body['total'] == 6 and len(body['ads']) == 6
    bare = next(a for a in body['ads'] if a['ad_id'] == '99')['row']
    assert bare['headline'] == NOT_DISCLOSED and bare['published_date'] == NOT_DISCLOSED
    assert bare['author'] == NOT_DISCLOSED and bare['url'] is None and bare['url_label'] == NOT_DISCLOSED


def test_date_labels(test_settings):
    ads = [fixture_ad('microsoft', '1', first_seen='2024-02-01T00:00:00Z', date_type='first_served'),
           fixture_ad('microsoft', '2', published_date='2024-03-03')]
    client = make_client(test_settings, all_spies(microsoft=SpyAdapter('microsoft', ads)).values())
    rows = {a['ad_id']: a['row'] for a in client.post('/api/ads/fetch', json={'company': 'A', 'platforms': ['microsoft']}).json()['ads']}
    assert rows['1']['published_date'] == '2024-02-01 (first served)'
    assert rows['2']['published_date'] == '2024-03-03'


def test_duplicates_removed_across_fetches(test_settings):
    ad = fixture_ad('meta', '1', headline='Same')
    client = make_client(test_settings, all_spies(meta=SpyAdapter('meta', [ad, ad])).values())
    first = client.post('/api/ads/fetch', json={'company': 'A', 'platforms': ['meta']}).json()
    client.post('/api/ads/fetch', json={'company': 'A', 'platforms': ['meta']})
    assert first['total'] == 1
    assert client.get('/api/ads').json()['total'] == 1
    same_copy = [fixture_ad('meta', '1', ad_copy='x'), fixture_ad('meta', '2', ad_copy='x')]
    client2 = make_client(test_settings, all_spies(meta=SpyAdapter('meta', same_copy)).values())
    assert client2.post('/api/ads/fetch', json={'company': 'B', 'platforms': ['meta']}).json()['total'] == 2


def test_filter_sort_paginate_detail(test_settings):
    ads = [fixture_ad('meta', '1', headline='Running shoes', first_seen='2024-01-10', date_type='delivery_start'),
           fixture_ad('meta', '2', headline='Football boots', first_seen='2024-06-10', date_type='delivery_start')]
    client = make_client(test_settings, all_spies(meta=SpyAdapter('meta', ads),
                                                  microsoft=SpyAdapter('microsoft', [fixture_ad('microsoft', '3')])).values())
    fid = client.post('/api/ads/fetch', json={'company': 'A', 'platforms': ['meta', 'microsoft']}).json()['fetch_id']
    assert client.get('/api/ads', params={'fetch_id': fid, 'q': 'boots'}).json()['total'] == 1
    assert client.get('/api/ads', params={'fetch_id': fid, 'platform': 'microsoft'}).json()['total'] == 1
    assert client.get('/api/ads', params={'fetch_id': fid, 'date_from': '2024-05-01'}).json()['total'] == 1
    desc = client.get('/api/ads', params={'fetch_id': fid, 'platform': 'meta', 'sort': 'published', 'order': 'desc'}).json()
    assert [a['ad_id'] for a in desc['ads']] == ['2', '1']
    page2 = client.get('/api/ads', params={'fetch_id': fid, 'page': 2, 'page_size': 2}).json()
    assert page2['total'] == 3 and len(page2['ads']) == 1
    pk = desc['ads'][0]['id']
    assert client.get(f'/api/ads/{pk}').json()['headline'] == 'Football boots'
    assert client.get('/api/ads/99999').status_code == 404


def test_exports_contain_normalized_results_and_respect_filters(test_settings):
    ads = [fixture_ad('meta', '1', headline='Alpha', ad_copy='=HYPERLINK("x")', author='Acme'),
           fixture_ad('meta', '2', headline='Beta')]
    client = make_client(test_settings, all_spies(meta=SpyAdapter('meta', ads)).values())
    fid = client.post('/api/ads/fetch', json={'company': 'A', 'platforms': ['meta']}).json()['fetch_id']
    data = client.get('/api/ads/export', params={'format': 'json', 'fetch_id': fid}).json()
    assert {d['ad_id'] for d in data} == {'1', '2'} and 'row' not in data[0]
    text = client.get('/api/ads/export', params={'format': 'csv', 'fetch_id': fid, 'q': 'Alpha'}).text.lstrip('﻿')
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1 and rows[0]['S.No.'] == '1' and rows[0]['Ad Platform'] == 'Meta'
    assert rows[0]['ad_copy'].startswith("'=")   # formula injection neutralised
    assert rows[0]['Author'] == 'Acme'


def test_live_registry_returns_no_demo_data(test_settings, monkeypatch):
    """Real adapters with no credentials and no network: nothing fabricated, no fake 'no_results'."""
    import httpx

    def offline(*_a, **_k):
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError('offline'))))

    registry = build_registry()
    registry['microsoft'].client_factory = offline
    registry['microsoft'].sleep = lambda s: __import__('asyncio').sleep(0)
    monkeypatch.setattr('adapters.meta.settings.meta_access_token', None)
    monkeypatch.setattr('adapters.google.settings.google_cloud_project', None)
    app = create_app(registry=registry, storage=Storage(test_settings.db_path), settings=test_settings)
    body = TestClient(app).post('/api/ads/fetch', json={'company': 'Nike', 'platforms': list(registry)}).json()
    assert body['total'] == 0 and body['ads'] == []
    statuses = {p: s['status'] for p, s in body['platforms'].items()}
    assert 'no_results' not in statuses.values()
    assert statuses['meta'] == statuses['google'] == statuses['linkedin'] == 'access_required'
    assert statuses['microsoft'] == 'error'
    assert all(body['platforms'][p]['fallback_url'] for p in ('meta', 'google', 'linkedin'))


def test_production_code_never_imports_fixtures():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for path in [*root.glob('*.py'), *root.glob('adapters/*.py'), *root.glob('services/*.py'), *root.glob('database/*.py')]:
        assert 'tests' not in path.read_text().replace('# tests', ''), path


def test_platform_status_has_capabilities_but_no_secrets(test_settings, monkeypatch):
    monkeypatch.setattr('adapters.meta.settings.meta_access_token', 'TOPSECRET')
    app = create_app(storage=Storage(test_settings.db_path), settings=test_settings)
    text = TestClient(app).get('/api/platforms/status').text
    assert 'TOPSECRET' not in text
    caps = {p['platform']: p for p in json.loads(text)['platforms']}
    assert caps['meta']['configured'] is True and caps['linkedin']['retrieval'] == 'link_only'
