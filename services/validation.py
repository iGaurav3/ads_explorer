"""Input validation, URL checks and secret redaction."""
from urllib.parse import urlsplit
import ipaddress
import re

HOSTNAME_RE = re.compile(r'^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$')
PLATFORMS = ('linkedin', 'meta', 'google', 'microsoft', 'tiktok', 'pinterest', 'snapchat', 'twitter')


def normalize_domain(value):
    """Accept 'nike.com', 'https://www.nike.com/path' -> 'nike.com'. Raises ValueError.

    The domain is only ever used for string matching; it is never fetched.
    """
    if not value:
        return None
    text = str(value).strip().lower()
    if '://' in text:
        text = urlsplit(text).hostname or ''
    text = text.split('/')[0].split(':')[0].strip('.')
    if text.startswith('www.'):
        text = text[4:]
    try:
        ipaddress.ip_address(text)
        raise ValueError('IP addresses are not accepted as a company domain')
    except ValueError as exc:
        if 'IP addresses' in str(exc):
            raise
    if not HOSTNAME_RE.match(text):
        raise ValueError('Invalid company domain')
    return text


def host_matches(url, domain):
    if not url or not domain:
        return False
    text = str(url).strip().lower()
    host = urlsplit(text if '://' in text else 'https://' + text).hostname or ''
    return host == domain or host.endswith('.' + domain)


def safe_url(value):
    """Return the URL if it is an absolute http(s) URL without credentials, else None."""
    if not value:
        return None
    text = str(value).strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        return None
    return text


def redact(text, secrets):
    out = str(text or '')
    for secret in secrets:
        if secret:
            out = out.replace(secret, '[redacted]')
    out = re.sub(r'(access_token=)[^&\s"]+', r'\1[redacted]', out)
    return out[:300]


def name_matches(candidate, company):
    a = ' '.join(str(candidate or '').casefold().split())
    b = ' '.join(str(company or '').casefold().split())
    return bool(a and b) and (a == b or b in a or a in b)


def match_rank(candidate, company):
    a = ' '.join(str(candidate or '').casefold().split())
    b = ' '.join(str(company or '').casefold().split())
    if a == b:
        return 0
    if a.startswith(b):
        return 1
    return 2 if b in a or a in b else 9
