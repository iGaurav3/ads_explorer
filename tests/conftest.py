"""Test helpers. Fixture records here are test data only and never reach the live app."""
import os
import sys
from pathlib import Path

os.environ['PUBLIC_ADS_NO_APP'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import pytest  # noqa: E402

from config import Settings  # noqa: E402


async def no_sleep(_seconds):
    return None


def mock_factory(handler):
    """Return a client_factory whose requests are answered by `handler(request) -> httpx.Response`."""
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def test_settings(tmp_path):
    s = Settings()
    s.db_path = tmp_path / 'ads.sqlite3'
    s.cache_ttl_seconds = 0
    s.meta_access_token = None
    s.google_cloud_project = None
    return s
