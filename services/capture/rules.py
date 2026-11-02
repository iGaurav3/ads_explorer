"""Rule-based parsing of ad-library pages the user captured in their own browser.

Each platform's page is split into one text segment per ad, anchored on the
ad's public ID (Meta "Library ID", LinkedIn and Google detail links). Fields
are only taken from the segment text; anything not found stays None.
"""
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlsplit
import re

from services.capture.page_text import LINK_RE, links_in, strip_links
from services.normalizer import NormalizedAd

PLATFORM_HOSTS = {
    'www.facebook.com': 'meta', 'facebook.com': 'meta', 'web.facebook.com': 'meta',
    'www.linkedin.com': 'linkedin', 'linkedin.com': 'linkedin',
    'adstransparency.google.com': 'google',
}

DATE = r'(?:\d{4}-\d{2}-\d{2}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4})'
DATE_FORMATS = ('%Y-%m-%d', '%d %b %Y', '%d %B %Y', '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y')
RANGE_RE = re.compile(rf'({DATE})\s*[-–—]\s*({DATE})')
CTA = {'learn more', 'shop now', 'sign up', 'download', 'book now', 'contact us', 'apply now', 'get offer', 'subscribe',
       'watch more', 'order now', 'send message', 'install now', 'get quote', 'listen now', 'see menu', 'play game',
       'donate now', 'get directions', 'call now', 'use app', 'register', 'request demo', 'view quote', 'get started'}

META_ID_RE = re.compile(r'Library ID:?\s*(\d{6,25})')
META_STARTED_RE = re.compile(rf'Started running on\s+({DATE})')
META_CHROME = re.compile(r'^(Sponsored|See ad details|See summary details|Platforms|Categories|Active|Inactive|'
                         r'Open Dropdown|This ad has multiple versions|EU transparency|About the advertiser|'
                         r'\d+ ads? use this creative and text\.?|Library ID.*|Started running on.*|' + DATE + r'.*)$', re.I)

LINKEDIN_LINK_RE = re.compile(r'https?://(?:www\.)?linkedin\.com/ad-library/detail/(\d+)')
LINKEDIN_RAN_RE = re.compile(rf'Ran from\s+({DATE})\s+to\s+({DATE})', re.I)
LINKEDIN_FORMATS = {'single image ad', 'video ad', 'carousel ad', 'document ad', 'text ad', 'message ad', 'event ad',
                    'conversation ad', 'spotlight ad', 'follower ad', 'job ad', 'thought leader ad'}
LINKEDIN_CHROME = re.compile(r'^(Promoted|View details|View ad|Ad|Paid for by.*|Ran from.*|Advertiser|Ad details)$', re.I)

GOOGLE_LINK_RE = re.compile(r'(?:https?://adstransparency\.google\.com)?/advertiser/(AR\d+)/creative/(CR\d+)')
GOOGLE_SHOWN_RE = re.compile(rf'(First|Last) shown:?\s*({DATE})', re.I)
GOOGLE_FORMAT_RE = re.compile(r'^Format:?\s*(Text|Image|Video)$', re.I)
GOOGLE_CHROME = re.compile(r'^(Verified|Ad details|See all ads|Shown in.*|First shown.*|Last shown.*|Format.*|'
                           r'Advertiser|Paid for by.*|Ad|\d+ ads?)$', re.I)


OWN_HOSTS = {
    'meta': ('facebook.com', 'instagram.com', 'fbcdn.net', 'fb.me'),
    'linkedin': ('linkedin.com', 'licdn.com', 'lnkd.in'),
    'google': ('google.com', 'googleusercontent.com', 'gstatic.com', 'youtube.com', 'ytimg.com'),
}
CHROME = {'meta': META_CHROME, 'linkedin': LINKEDIN_CHROME, 'google': GOOGLE_CHROME}
UI_BUTTONS = {'see ad details', 'see summary details', 'view details', 'view ad', 'see all ads', 'ad details'}


def is_page_chrome(platform, field, value):
    """True for library UI labels (buttons, format badges) that an LLM may mistake for ad content."""
    text = ' '.join(str(value or '').split())
    if text.casefold() in UI_BUTTONS or CHROME[platform].match(text):
        return True
    if field != 'creative_type' and text.casefold() in LINKEDIN_FORMATS:
        return True
    return field != 'call_to_action' and text.casefold() in CTA


def is_own_host(platform, url):
    host = (urlsplit(str(url or '')).hostname or '').lower()
    return any(host == h or host.endswith('.' + h) for h in OWN_HOSTS[platform])


def platform_for_url(url):
    try:
        parts = urlsplit(str(url or ''))
    except ValueError:
        return None
    if parts.scheme != 'https':
        return None
    return PLATFORM_HOSTS.get((parts.hostname or '').lower())


def parse_date(text):
    value = ' '.join(str(text or '').replace('.', ' ').split())
    value = re.sub(r'\s+,', ',', value)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def search_countries(page_url):
    """ISO-2 country filter of the captured search page, if any (it limits which ads the page lists)."""
    qs = parse_qs(urlsplit(page_url).query)
    raw = (qs.get('country') or qs.get('region') or qs.get('countries') or [''])[0]
    codes = [c.strip().upper() for c in raw.split(',') if re.fullmatch(r'[A-Za-z]{2}', c.strip())]
    return ','.join(codes) or None


def _lines(text):
    return [line for line in strip_links(text).splitlines() if line]


def _external_link(text, own_hosts):
    for href in links_in(text):
        parts = urlsplit(href)
        host = (parts.hostname or '').lower()
        if host == 'l.facebook.com' and parts.path == '/l.php':
            target = parse_qs(parts.query).get('u', [''])[0]
            return unquote(target) or None
        if parts.scheme in ('http', 'https') and host and not any(host == h or host.endswith('.' + h) for h in own_hosts):
            return href
    return None


def _segments_by_link(text, link_re):
    """Split at each ad-detail link: a segment is the text since the previous one, up to and including its link."""
    segments, start, seen = [], 0, set()
    for match in LINK_RE.finditer(text):
        found = link_re.search(match.group(1))
        if not found:
            continue
        key = found.groups()
        if key in seen:  # the same card often links its ID twice (image + "View details")
            if segments and segments[-1]['ids'] == key:
                segments[-1]['text'] = text[segments[-1]['start']:match.end()]
            start = match.end()
            continue
        seen.add(key)
        segments.append({'ids': key, 'start': start, 'text': text[start:match.end()]})
        start = match.end()
    return segments


def _base(platform, page_url, company, segment_text, **fields):
    return NormalizedAd(platform=platform, company_name=company, country=search_countries(page_url),
                        source_type='user_capture',
                        source_metadata={'capture': {'page_url': page_url, 'method': 'rules',
                                                     'segment_text': strip_links(segment_text)[:4000],
                                                     'raw_segment': segment_text[:6000]}},
                        **fields)


def parse_meta(text, page_url, company):
    lines = text.splitlines()
    anchors = [i for i, line in enumerate(lines) if META_ID_RE.search(line)]
    ads = []
    for n, i in enumerate(anchors):
        start = i - 1 if i > 0 and lines[i - 1].strip() in ('Active', 'Inactive') else i
        end = anchors[n + 1] - 1 if n + 1 < len(anchors) else len(lines)
        if n + 1 < len(anchors) and lines[anchors[n + 1] - 1].strip() not in ('Active', 'Inactive'):
            end = anchors[n + 1]
        segment = '\n'.join(lines[start:end])
        ad_id = META_ID_RE.search(lines[i]).group(1)
        status = {'Active': 'active', 'Inactive': 'inactive'}.get(lines[start].strip(), 'unknown')
        first = last = None
        if m := META_STARTED_RE.search(segment):
            first = parse_date(m.group(1))
        elif m := RANGE_RE.search(segment):
            first, last = parse_date(m.group(1)), parse_date(m.group(2))

        plain = _lines(segment)
        advertiser = cta = headline = description = None
        body = []
        if 'Sponsored' in plain:
            k = plain.index('Sponsored')
            advertiser = plain[k - 1] if k > 0 and not META_CHROME.match(plain[k - 1]) else None
            after = [x for x in plain[k + 1:] if not META_CHROME.match(x)]
            domain_at = next((j for j, x in enumerate(after) if re.fullmatch(r'[A-Z0-9.-]+\.[A-Z]{2,}', x)), None)
            for x in after:
                if x.casefold() in CTA:
                    cta = cta or x
            body = after if domain_at is None else after[:domain_at]
            tail = [] if domain_at is None else [x for x in after[domain_at + 1:] if x.casefold() not in CTA]
            headline = tail[0] if tail else None
            description = tail[1] if len(tail) > 1 else None
        body = [x for x in body if x.casefold() not in CTA]
        ads.append(_base('meta', page_url, company, segment, ad_id=ad_id, advertiser_name=advertiser, author=advertiser,
                         headline=headline, description=description, ad_copy='\n'.join(body) or None,
                         call_to_action=cta, ad_url=f'https://www.facebook.com/ads/library/?id={ad_id}',
                         landing_page_url=_external_link(segment, OWN_HOSTS['meta']),
                         first_seen=first, last_seen=last, date_type='delivery_start' if first else None,
                         ad_status=status))
    return ads


def parse_linkedin(text, page_url, company):
    detail = LINKEDIN_LINK_RE.search(page_url)
    segments = [{'ids': (detail.group(1),), 'text': text}] if detail else _segments_by_link(text, LINKEDIN_LINK_RE)
    ads = []
    for seg in segments:
        segment, (ad_id,) = seg['text'], seg['ids']
        plain = _lines(segment)
        first = last = None
        if m := (LINKEDIN_RAN_RE.search(segment) or RANGE_RE.search(segment)):
            first, last = parse_date(m.group(1)), parse_date(m.group(2))
        payer = next((m.group(1).strip() for m in (re.match(r'Paid for by:?\s*(.+)', x, re.I) for x in plain) if m), None)
        creative = next((x for x in plain if x.casefold() in LINKEDIN_FORMATS), None)
        cta = next((x for x in plain if x.casefold() in CTA), None)
        if 'Promoted' in plain:  # card layout: advertiser name sits directly above "Promoted"
            k = plain.index('Promoted')
            head = [plain[k - 1]] if k > 0 and not LINKEDIN_CHROME.match(plain[k - 1]) else [None]
            plain = head + plain[k + 1:]
        content = [x for x in plain if x is None or (not LINKEDIN_CHROME.match(x) and x.casefold() not in LINKEDIN_FORMATS
                   and x.casefold() not in CTA and not RANGE_RE.fullmatch(x))]
        advertiser = content[0] if content else None
        ads.append(_base('linkedin', page_url, company, segment, ad_id=ad_id, advertiser_name=advertiser,
                         author=payer or advertiser, ad_copy='\n'.join(content[1:]) or None,
                         creative_type=creative.lower().removesuffix(' ad') if creative else None, call_to_action=cta,
                         ad_url=f'https://www.linkedin.com/ad-library/detail/{ad_id}',
                         landing_page_url=_external_link(segment, OWN_HOSTS['linkedin']),
                         first_seen=first, last_seen=last, date_type='first_shown' if first else None))
    return ads


def parse_google(text, page_url, company):
    detail = GOOGLE_LINK_RE.search(urlsplit(page_url).path)
    segments = [{'ids': detail.groups(), 'text': text}] if detail else _segments_by_link(text, GOOGLE_LINK_RE)
    region = search_countries(page_url)
    ads = []
    for seg in segments:
        segment, (advertiser_id, ad_id) = seg['text'], seg['ids']
        plain = _lines(segment)
        dates = {m.group(1).lower(): parse_date(m.group(2)) for m in GOOGLE_SHOWN_RE.finditer(segment)}
        fmt = next((m.group(1).lower() for m in (GOOGLE_FORMAT_RE.match(x) for x in plain) if m), None)
        payer = next((m.group(1).strip() for m in (re.match(r'Paid for by:?\s*(.+)', x, re.I) for x in plain) if m), None)
        content = [x for x in plain if not GOOGLE_CHROME.match(x)]
        advertiser = content[0] if content else None
        url = f'https://adstransparency.google.com/advertiser/{advertiser_id}/creative/{ad_id}'
        ads.append(_base('google', page_url, company, segment, ad_id=ad_id, advertiser_name=advertiser,
                         author=payer or advertiser, ad_copy='\n'.join(content[1:]) or None, creative_type=fmt,
                         ad_url=url + (f'?region={region}' if region and ',' not in region else ''),
                         landing_page_url=_external_link(segment, OWN_HOSTS['google']),
                         first_seen=dates.get('first'), last_seen=dates.get('last'),
                         date_type='first_shown' if dates.get('first') else None))
        ads[-1].source_metadata['advertiser_id'] = advertiser_id
    return ads


PARSERS = {'meta': parse_meta, 'linkedin': parse_linkedin, 'google': parse_google}


def parse(platform, text, page_url, company):
    return PARSERS[platform](text, page_url, company)
