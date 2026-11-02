import asyncio
from datetime import date

from adapters.base import FetchRequest
from adapters.google import GoogleAdapter, QueryTooLarge
from config import settings


class FakeRunner:
    """TEST FIXTURE: answers the two queries with synthetic rows shaped like creative_stats."""

    def __init__(self, too_large=False):
        self.calls = []
        self.too_large = too_large

    def run(self, sql, params):
        self.calls.append((sql, params))
        if self.too_large:
            raise QueryTooLarge(50 * 1024**3)
        if 'GROUP BY advertiser_id' in sql:
            return [{'advertiser_id': 'AR1', 'name': 'Fixture Shoes Inc', 'creatives': 2},
                    {'advertiser_id': 'AR9', 'name': 'Totally Different', 'creatives': 50}], 1024**3
        return [
            {'advertiser_id': 'AR1', 'advertiser_disclosed_name': 'Fixture Shoes Inc', 'advertiser_legal_name': 'Fixture Shoes Incorporated',
             'creative_id': 'CR1', 'creative_page_url': 'https://adstransparency.google.com/advertiser/AR1/creative/CR1',
             'ad_format_type': 'VIDEO', 'topic': 'Apparel', 'ad_funded_by': None,
             'regions': [{'region_code': 'DE', 'first_shown': date(2024, 1, 5), 'last_shown': date(2024, 2, 1)},
                         {'region_code': 'FR', 'first_shown': date(2023, 12, 1), 'last_shown': date(2024, 1, 9)}]},
            {'advertiser_id': 'AR1', 'advertiser_disclosed_name': 'Fixture Shoes Inc', 'creative_id': 'CR2',
             'creative_page_url': 'https://evil.example/CR2', 'ad_format_type': 'TEXT', 'ad_funded_by': 'Fixture Agency',
             'regions': []},
        ], 2 * 1024**3


def run(req, runner):
    return asyncio.run(GoogleAdapter(runner_factory=lambda: runner).fetch_ads(req))


def test_not_configured_is_access_required(monkeypatch):
    monkeypatch.setattr(settings, 'google_cloud_project', None)
    result = asyncio.run(GoogleAdapter().fetch_ads(FetchRequest('Fixture Shoes')))
    assert result.status == 'access_required' and result.setup_hint
    assert result.fallback_url.startswith('https://adstransparency.google.com/')


def test_maps_creatives():
    runner = FakeRunner()
    result = run(FetchRequest('Fixture Shoes', country='DE', start_date=date(2024, 1, 1)), runner)
    assert result.status == 'success'
    assert runner.calls[1][1]['advertiser_ids'] == ('ARRAY<STRING>', ['AR1'])
    assert runner.calls[1][1]['country'] == ('STRING', 'DE')
    cr1, cr2 = result.ads
    assert cr1.ad_id == 'CR1' and cr1.creative_type == 'video'
    assert cr1.ad_url == 'https://adstransparency.google.com/advertiser/AR1/creative/CR1'
    assert cr1.first_seen == '2023-12-01' and cr1.last_seen == '2024-02-01' and cr1.date_type == 'first_shown'
    assert cr1.published_date is None and cr1.headline is None
    assert cr1.author == 'Fixture Shoes Inc'
    assert cr2.ad_url is None                 # non-Google host rejected
    assert cr2.author == 'Fixture Agency'     # payer when different
    assert cr2.first_seen is None


def test_cost_guard():
    result = run(FetchRequest('Fixture Shoes'), FakeRunner(too_large=True))
    assert result.status == 'error' and 'GB' in result.error and not result.ads
