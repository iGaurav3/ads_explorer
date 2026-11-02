"""Common adapter contract shared by every platform connector."""
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone

STATUSES = (
    'success', 'no_results', 'partial_results', 'access_required',
    'unsupported_without_auth', 'rate_limited', 'blocked', 'error',
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@dataclass
class FetchRequest:
    company_name: str
    company_domain: str | None = None
    country: str | None = None          # ISO-3166 alpha-2
    start_date: date | None = None
    end_date: date | None = None
    limit: int = 100
    meta_page_ids: list[str] = field(default_factory=list)

    def cache_key(self):
        return {
            'company': self.company_name.casefold().strip(), 'domain': self.company_domain,
            'country': self.country, 'start': str(self.start_date or ''), 'end': str(self.end_date or ''),
            'limit': self.limit, 'meta_page_ids': sorted(self.meta_page_ids),
        }


@dataclass
class FetchResult:
    platform: str
    status: str
    ads: list = field(default_factory=list)
    coverage: str = ''
    warnings: list = field(default_factory=list)
    error: str | None = None
    setup_hint: str | None = None
    fallback_url: str | None = None
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    cached: bool = False

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f'Unknown status {self.status}')

    def summary(self):
        data = asdict(self)
        data.pop('ads')
        data['record_count'] = len(self.ads)
        return data


class AdapterError(Exception):
    """Raised inside adapters to end a fetch with a specific status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class BaseAdapter:
    platform = ''
    display_name = ''
    coverage = ''
    requires_credentials = False
    retrieval = 'live'  # live | link_only

    def is_configured(self):
        return True

    def setup_hint(self):
        return None

    def fallback_url(self, req: FetchRequest):
        return None

    async def fetch_ads(self, req: FetchRequest) -> FetchResult:
        raise NotImplementedError

    def result(self, req, status, ads=(), **kwargs):
        kwargs.setdefault('coverage', self.coverage)
        kwargs.setdefault('fallback_url', self.fallback_url(req))
        return FetchResult(platform=self.platform, status=status, ads=list(ads), **kwargs)

    def capability(self):
        return {
            'platform': self.platform, 'name': self.display_name, 'retrieval': self.retrieval,
            'requires_credentials': self.requires_credentials, 'configured': self.is_configured(),
            'coverage': self.coverage, 'setup_hint': None if self.is_configured() else self.setup_hint(),
        }
