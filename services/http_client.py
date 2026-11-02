"""Small async JSON client: host allow-list, timeouts, size cap and backoff."""
from urllib.parse import urlsplit
import asyncio
import json
import random

import httpx

MAX_BYTES = 5_000_000
USER_AGENT = 'PublicAdsExplorer/2.0 (+public ad transparency research)'


class HttpError(Exception):
    def __init__(self, status_code, message, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class NetworkError(Exception):
    pass


def new_client(timeout):
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})


async def get_json(client, url, *, params=None, headers=None, allowed_hosts=(), retries=3, sleep=asyncio.sleep):
    host = urlsplit(url).hostname
    if host not in allowed_hosts:
        raise NetworkError(f'Host {host} is not allowed for this connector')
    attempt, rate_limit_retried = 0, False
    while True:
        try:
            response = await client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt < retries:
                await sleep(_backoff(attempt))
                attempt += 1
                continue
            raise NetworkError(f'Network error: {type(exc).__name__}') from exc

        if response.status_code == 429 and not rate_limit_retried:
            rate_limit_retried = True
            await sleep(min(_retry_after(response), 10))
            continue
        if response.status_code >= 500 and attempt < retries:
            await sleep(_backoff(attempt))
            attempt += 1
            continue

        body = response.content[:MAX_BYTES]
        try:
            payload = json.loads(body.decode('utf-8')) if body else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if response.status_code >= 400:
            raise HttpError(response.status_code, f'HTTP {response.status_code}', payload)
        if payload is None and body:
            raise HttpError(response.status_code, 'Response was not JSON')
        return payload


def _backoff(attempt):
    return 0.5 * (2 ** attempt) + random.uniform(0, 0.25)


def _retry_after(response):
    try:
        return float(response.headers.get('Retry-After', '2'))
    except ValueError:
        return 2.0
