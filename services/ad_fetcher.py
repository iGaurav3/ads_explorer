"""Runs the selected platform adapters concurrently and persists their results.

Only adapters for the selected platforms are invoked. Each adapter runs under
its own timeout and exception guard, so one failure never discards another
platform's records.
"""
import asyncio
import logging

from adapters.base import FetchResult, now_iso
from services.validation import redact

log = logging.getLogger(__name__)


class AdFetcher:
    def __init__(self, registry, storage, settings):
        self.registry = registry
        self.storage = storage
        self.settings = settings

    async def fetch(self, fetch_id, req, platforms):
        params = req.cache_key()
        self.storage.create_fetch(fetch_id, params, platforms)
        semaphore = asyncio.Semaphore(self.settings.max_platform_concurrency)

        async def run(platform):
            async with semaphore:
                return platform, await self._run_one(fetch_id, platform, req, params)

        results = dict(await asyncio.gather(*(run(p) for p in platforms)))
        return results

    async def _run_one(self, fetch_id, platform, req, params):
        adapter = self.registry[platform]
        hit = self.storage.cached(platform, params, self.settings.cache_ttl_seconds)
        if hit:
            summary, ids = hit
            self.storage.link_ads(fetch_id, platform, ids)
            summary = {**summary, 'cached': True}
            self.storage.set_status(fetch_id, platform, summary['status'], summary)
            return summary

        self.storage.set_status(fetch_id, platform, 'running', {'started_at': now_iso()})
        try:
            result = await asyncio.wait_for(adapter.fetch_ads(req), timeout=self.settings.platform_timeout)
        except asyncio.TimeoutError:
            result = adapter.result(req, 'error', error=f'Timed out after {self.settings.platform_timeout:.0f}s.', finished_at=now_iso())
        except Exception as exc:  # an adapter bug must not affect other platforms
            log.exception('Adapter %s failed', platform)
            result = adapter.result(req, 'error', error=redact(f'{type(exc).__name__}: {exc}', self.settings.secrets()), finished_at=now_iso())

        result.finished_at = result.finished_at or now_iso()
        self.storage.save_ads(fetch_id, result.ads)
        summary = result.summary()
        self.storage.set_status(fetch_id, platform, result.status, summary)
        return summary


__all__ = ['AdFetcher', 'FetchResult']
