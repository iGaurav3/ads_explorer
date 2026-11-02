"""Runtime settings, read from the environment or a local `.env` file.

Secrets (e.g. META_ACCESS_TOKEN) are only ever read here; they must never be
logged, stored in the database or returned by the API.
"""
from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / '.env')
except ImportError:  # python-dotenv is optional
    pass


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv('ADS_DB_PATH', ROOT / 'data' / 'ads.sqlite3')))
    cache_ttl_seconds: int = field(default_factory=lambda: _int('CACHE_TTL_SECONDS', 3600))
    http_timeout: float = field(default_factory=lambda: float(os.getenv('HTTP_TIMEOUT', '15')))
    platform_timeout: float = field(default_factory=lambda: float(os.getenv('PLATFORM_TIMEOUT', '240')))
    max_platform_concurrency: int = field(default_factory=lambda: _int('MAX_PLATFORM_CONCURRENCY', 4))

    microsoft_max_details: int = field(default_factory=lambda: _int('MICROSOFT_MAX_DETAILS', 50))
    microsoft_timeout: float = field(default_factory=lambda: float(os.getenv('MICROSOFT_TIMEOUT', '60')))

    meta_access_token: str | None = field(default_factory=lambda: os.getenv('META_ACCESS_TOKEN') or None)
    meta_api_version: str = field(default_factory=lambda: os.getenv('META_API_VERSION', 'v26.0'))

    google_index_path: Path = field(default_factory=lambda: Path(os.getenv('GOOGLE_INDEX_PATH', ROOT / 'data' / 'google_transparency.sqlite3')))
    google_cloud_project: str | None = field(default_factory=lambda: os.getenv('GOOGLE_CLOUD_PROJECT') or None)
    google_max_bytes_billed: int = field(default_factory=lambda: _int('GOOGLE_MAX_BYTES_BILLED', 10 * 1024**3))

    ollama_url: str = field(default_factory=lambda: os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434'))
    ollama_model: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'llama3'))
    capture_llm_max_segments: int = field(default_factory=lambda: _int('CAPTURE_LLM_MAX_SEGMENTS', 10))
    capture_max_bytes: int = field(default_factory=lambda: _int('CAPTURE_MAX_BYTES', 8 * 1024**2))

    def secrets(self):
        return [s for s in (self.meta_access_token,) if s]


settings = Settings()
