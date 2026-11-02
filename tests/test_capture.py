"""Browser-capture pipeline: page rules, grounding of LLM output, and the /api/capture endpoint."""
import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from database.storage import Storage
from server import create_app
from services.capture.grounding import ground
from services.capture.llm import OllamaExtractor
from services.capture.page_text import html_to_text
from services.capture.rules import parse, parse_date, platform_for_url
from services.capture.service import CaptureService
from tests.fixtures.capture import pages


def test_platform_detection_requires_https_library_host():
    assert platform_for_url(pages.META_URL) == 'meta'
    assert platform_for_url(pages.LINKEDIN_URL) == 'linkedin'
    assert platform_for_url(pages.GOOGLE_URL) == 'google'
    assert platform_for_url('http://www.facebook.com/ads/library/') is None
    assert platform_for_url('https://evil.example/ads/library/') is None


def test_parse_date_formats():
    assert parse_date('12 Oct 2025') == '2025-10-12'
    assert parse_date('Oct 1, 2025') == '2025-10-01'
    assert parse_date('January 5, 2026') == '2026-01-05'
    assert parse_date('2026-03-01') == '2026-03-01'
    assert parse_date('soon') is None


def test_meta_cards():
    ads = parse('meta', pages.META_TEXT, pages.META_URL, 'Examplecorp')
    assert [a.ad_id for a in ads] == ['111222333444', '555666777888']
    first, second = ads
    assert first.ad_status == 'active' and second.ad_status == 'inactive'
    assert first.first_seen == '2025-10-12' and first.date_type == 'delivery_start' and first.last_seen is None
    assert (second.first_seen, second.last_seen) == ('2025-10-01', '2025-10-20')
    assert first.advertiser_name == 'Examplecorp'
    assert first.ad_copy == 'Cloud security for every team.\nStart a free trial today.'
    assert first.headline == 'Secure your cloud in minutes' and first.description == 'Zero setup required'
    assert first.call_to_action == 'Learn more' and second.call_to_action == 'Shop now'
    assert first.landing_page_url == 'https://examplecorp.test/trial?utm_source=fb'
    assert first.ad_url == 'https://www.facebook.com/ads/library/?id=111222333444'
    assert first.country == 'GB' and first.source_type == 'user_capture'


def test_linkedin_search_and_detail():
    ads = parse('linkedin', pages.LINKEDIN_TEXT, pages.LINKEDIN_URL, 'Examplecorp')
    assert [a.ad_id for a in ads] == ['987654321', '987654322']
    assert [a.advertiser_name for a in ads] == ['Examplecorp', 'Examplecorp']
    assert ads[0].ad_copy == 'AI operations that scale with you.'
    assert [a.creative_type for a in ads] == ['single image', 'video']
    assert ads[0].first_seen is None  # the search card shows no dates; none are invented
    [detail] = parse('linkedin', pages.LINKEDIN_DETAIL_TEXT, pages.LINKEDIN_DETAIL_URL, 'Examplecorp')
    assert detail.ad_id == '987654321' and detail.author == 'Examplecorp Holdings Ltd'
    assert (detail.first_seen, detail.last_seen) == ('2026-01-05', '2026-03-01')
    assert detail.landing_page_url == 'https://examplecorp.test/aiops'
    assert detail.ad_url == 'https://www.linkedin.com/ad-library/detail/987654321'


def test_google_search_and_detail():
    ads = parse('google', pages.GOOGLE_TEXT, pages.GOOGLE_URL, 'Examplecorp')
    assert [a.ad_id for a in ads] == ['CR11111111111', 'CR22222222222']
    assert ads[0].ad_url == 'https://adstransparency.google.com/advertiser/AR01234567890/creative/CR11111111111?region=DE'
    assert ads[0].ad_copy is None and ads[0].source_metadata['advertiser_id'] == 'AR01234567890'
    [detail] = parse('google', pages.GOOGLE_DETAIL_TEXT, pages.GOOGLE_DETAIL_URL, 'Examplecorp')
    assert detail.creative_type == 'text' and detail.last_seen == '2025-10-25' and detail.first_seen is None
    assert detail.ad_copy == 'Examplecorp cloud backup - plans from 5 EUR'


def test_saved_html_skips_scripts():
    text = html_to_text(pages.META_HTML)
    assert '999' not in text
    [ad] = parse('meta', text, pages.META_URL, 'Examplecorp')
    assert ad.ad_id == '123456789012' and ad.ad_copy == 'Spring launch & more' and ad.first_seen == '2026-02-03'


def test_grounding_drops_anything_not_on_the_page():
    source = pages.LINKEDIN_DETAIL_TEXT
    fields, dropped = ground({
        'headline': 'AI operations that scale with you.',
        'advertiser_name': 'Totally Different Inc',          # invented
        'landing_page_url': 'https://examplecorp.test/aiops',
        'ad_id': '424242',                                   # invented
        'first_date_text': 'Jan 5, 2026',
        'last_date_text': 'Apr 9, 2026',                     # invented
    }, source)
    assert fields == {'headline': 'AI operations that scale with you.', 'landing_page_url': 'https://examplecorp.test/aiops',
                      'first_seen': '2026-01-05'}
    assert set(dropped) == {'advertiser_name', 'ad_id', 'last_seen'}


def ollama(handler):
    return OllamaExtractor('http://127.0.0.1:11434', 'llama3',
                           client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def chat_reply(payload):
    return httpx.Response(200, json={'message': {'content': json.dumps(payload)}})


def test_llm_fills_only_missing_fields_with_grounded_values(test_settings):
    def handler(request):
        return chat_reply({'advertiser_name': 'Examplecorp', 'ad_copy': 'Data analytics made simple.',
                           'headline': 'Data analytics made simple.', 'call_to_action': 'Learn more',
                           'description': 'An invented line', 'first_date_text': 'Feb 3, 2099'})

    storage = Storage(test_settings.db_path)
    service = CaptureService(storage, test_settings, ollama(handler))
    result = asyncio.run(service.ingest(page_url=pages.META_URL, text=pages.META_VARIANT_TEXT, fetch_id='abcd1234',
                                        company='Examplecorp'))
    assert result['captured'] == 1 and result['method'] == 'rules+llm'
    _, [row] = storage.query_ads({'fetch_id': 'abcd1234'}, page_size=None)
    assert row['advertiser_name'] == 'Examplecorp' and row['ad_copy'] == 'Data analytics made simple.'
    assert row['headline'] is None              # a copy of the ad text is not a headline
    assert row['call_to_action'] == 'Learn more'
    assert row['description'] is None           # not on the page
    assert row['first_seen'] == '2026-03-02'    # rule value kept
    assert 'raw_segment' not in row['source_metadata']['capture']


def test_llm_output_that_is_library_ui_is_dropped(test_settings):
    calls = []

    def handler(request):
        calls.append(1)
        return chat_reply({'advertiser_name': 'Verified', 'ad_copy': 'Ad details', 'call_to_action': 'View details',
                           'landing_page_url': 'https://adstransparency.google.com/advertiser/AR01234567890/creative/CR11111111111?region=DE'})

    storage = Storage(test_settings.db_path)
    service = CaptureService(storage, test_settings, ollama(handler))
    asyncio.run(service.ingest(page_url=pages.GOOGLE_URL, text=pages.GOOGLE_TEXT, fetch_id='abcd1239'))
    _, rows = storage.query_ads({'fetch_id': 'abcd1239'}, page_size=None)
    assert len(calls) == 2  # Google cards have no text, so the LLM is asked
    for row in rows:
        assert row['advertiser_name'] == 'Examplecorp'
        assert (row['ad_copy'], row['call_to_action'], row['landing_page_url']) == (None, None, None)


def test_llm_skipped_when_rules_found_the_ad_text(test_settings):
    def handler(request):
        raise AssertionError('LLM should not be called')

    service = CaptureService(Storage(test_settings.db_path), test_settings, ollama(handler))
    result = asyncio.run(service.ingest(page_url=pages.LINKEDIN_URL, text=pages.LINKEDIN_TEXT, fetch_id='abcd123a'))
    assert result['captured'] == 2 and result['method'] == 'rules' and not result['warnings']


def test_llm_page_extraction_keeps_only_identifiable_grounded_ads(test_settings):
    def handler(request):
        return chat_reply({'ads': [
            {'advertiser_name': 'Examplecorp', 'ad_copy': 'Enterprise automation, simplified.'},
            {'advertiser_name': 'Examplecorp', 'ad_copy': 'A made-up ad that is not on the page.'},
            {'advertiser_name': 'Examplecorp', 'ad_copy': 'Single image ad', 'call_to_action': 'View details'},
        ]})

    storage = Storage(test_settings.db_path)
    service = CaptureService(storage, test_settings, ollama(handler))
    result = asyncio.run(service.ingest(page_url=pages.UNANCHORED_URL, text=pages.UNANCHORED_TEXT, fetch_id='abcd1235'))
    assert result['captured'] == 1 and result['method'] == 'llm'
    _, [row] = storage.query_ads({'fetch_id': 'abcd1235'}, page_size=None)
    assert row['ad_copy'] == 'Enterprise automation, simplified.' and row['ad_url'] is None


def test_llm_down_falls_back_to_rules(test_settings):
    def handler(request):
        raise httpx.ConnectError('refused')

    service = CaptureService(Storage(test_settings.db_path), test_settings, ollama(handler))
    result = asyncio.run(service.ingest(page_url=pages.GOOGLE_URL, text=pages.GOOGLE_TEXT, fetch_id='abcd1236'))
    assert result['captured'] == 2 and result['method'] == 'rules' and result['warnings']


def client(test_settings):
    def handler(request):
        raise httpx.ConnectError('no ollama in tests')
    app = create_app(storage=Storage(test_settings.db_path), settings=test_settings, llm=ollama(handler))
    return TestClient(app)


def test_capture_endpoint_accumulates_and_reports_partial(test_settings):
    c = client(test_settings)
    body = {'page_url': pages.META_URL, 'text': pages.META_TEXT, 'fetch_id': 'abcd1237', 'company': 'Examplecorp'}
    first = c.post('/api/capture', json=body).json()
    again = c.post('/api/capture', json=body).json()  # same page twice: deduplicated
    assert first['captured'] == 2 and again['status']['record_count'] == 2
    status = c.get('/api/platforms/status', params={'fetch_id': 'abcd1237'}).json()
    meta = next(p for p in status['platforms'] if p['platform'] == 'meta')
    assert meta['last']['status'] == 'partial_results' and meta['last']['record_count'] == 2
    ads = c.get('/api/ads', params={'fetch_id': 'abcd1237'}).json()
    assert ads['total'] == 2 and {a['row']['platform'] for a in ads['ads']} == {'Meta'}
    assert again['status']['status'] == 'partial_results' and len(again['status']['captured_pages']) == 2


def test_capture_endpoint_rejects_bad_input(test_settings):
    c = client(test_settings)
    assert c.post('/api/capture', json={'page_url': 'https://evil.example/x', 'text': 'Library ID: 123456'}).status_code == 422
    assert c.post('/api/capture', json={'page_url': pages.META_URL}).status_code == 422
    raw = json.dumps({'page_url': pages.META_URL, 'text': pages.META_TEXT})
    assert c.post('/api/capture', content=raw, headers={'Content-Type': 'text/plain'}).status_code in (415, 422)


def test_unrecognized_page_is_an_error_not_no_results(test_settings):
    c = client(test_settings)
    res = c.post('/api/capture', json={'page_url': pages.META_URL, 'text': 'Nothing here', 'fetch_id': 'abcd1238'}).json()
    assert res['captured'] == 0 and res['status']['status'] == 'error'


def test_llm_status_reports_missing_ollama(test_settings):
    assert client(test_settings).get('/api/llm/status').json()['available'] is False
