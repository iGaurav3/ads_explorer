"""Unified advertisement record and the display rules for the results table.

`None` always means "the source did not disclose this value". Nothing here may
substitute retrieval time for a publication date or invent URLs/authors.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json

from services.validation import safe_url

NOT_DISCLOSED = 'Not disclosed'

PLATFORM_LABELS = {
    'linkedin': 'LinkedIn', 'meta': 'Meta', 'google': 'Google', 'microsoft': 'Microsoft',
    'tiktok': 'TikTok', 'pinterest': 'Pinterest', 'snapchat': 'Snapchat', 'twitter': 'X / Twitter',
}

# date_type -> label suffix shown next to a non-publication date
DATE_TYPE_LABELS = {
    'published': '',
    'first_served': 'first served',
    'delivery_start': 'delivery start',
    'first_shown': 'first shown',
}


@dataclass
class NormalizedAd:
    platform: str
    ad_id: str | None = None
    company_name: str | None = None
    advertiser_name: str | None = None
    headline: str | None = None
    description: str | None = None
    ad_copy: str | None = None
    creative_type: str | None = None
    call_to_action: str | None = None
    creative_url: str | None = None
    ad_url: str | None = None
    landing_page_url: str | None = None
    published_date: str | None = None
    date_type: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    author: str | None = None
    country: str | None = None
    ad_status: str = 'unknown'
    source_type: str | None = None
    retrieved_at: str | None = None
    source_metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ('ad_url', 'landing_page_url', 'creative_url'):
            setattr(self, name, safe_url(getattr(self, name)))
        for name in ('ad_id', 'advertiser_name', 'headline', 'description', 'ad_copy', 'author'):
            value = getattr(self, name)
            if value is not None:
                value = str(value).strip()
                setattr(self, name, value or None)
        if self.retrieved_at is None:
            self.retrieved_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    def to_dict(self):
        return asdict(self)


def short_date(value):
    """Return YYYY-MM-DD for ISO-ish date/time strings, else None."""
    if not value:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == '-' and text[7] == '-' else None


def published_date_label(ad):
    if ad.get('published_date'):
        return short_date(ad['published_date']) or ad['published_date']
    if ad.get('first_seen'):
        label = DATE_TYPE_LABELS.get(ad.get('date_type') or '', ad.get('date_type') or '')
        day = short_date(ad['first_seen']) or ad['first_seen']
        return f'{day} ({label})' if label else day
    return NOT_DISCLOSED


def to_table_row(ad):
    """Display values for the six mandatory columns (S.No. is assigned by the caller)."""
    nd = lambda v: v if v not in (None, '') else NOT_DISCLOSED  # noqa: E731
    return {
        'platform': PLATFORM_LABELS.get(ad['platform'], ad['platform']),
        'headline': nd(ad.get('headline')),
        'body': nd(ad.get('ad_copy') or ad.get('description')),
        'creative_type': nd(ad.get('creative_type')),
        'call_to_action': nd(ad.get('call_to_action')),
        'ad_id': nd(ad.get('ad_id')),
        'landing_page_url': ad.get('landing_page_url'),
        'url': ad.get('ad_url'),
        'url_label': ad.get('ad_url') or NOT_DISCLOSED,
        'published_date': published_date_label(ad),
        'author': nd(ad.get('author') or ad.get('advertiser_name')),
    }


def dedupe_key(ad: NormalizedAd):
    """Platform-scoped ad ID; without an ID, a hash of the complete record.

    Two ID-less records only collapse when every field (including source
    metadata) is identical, so ads that merely share copy are kept apart.
    """
    if ad.ad_id:
        return 'id:' + ad.ad_id
    body = ad.to_dict()
    body.pop('retrieved_at', None)
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return 'sha256:' + hashlib.sha256(raw.encode('utf-8')).hexdigest()


def dedupe(ads):
    seen, out = set(), []
    for ad in ads:
        key = (ad.platform, dedupe_key(ad))
        if key not in seen:
            seen.add(key)
            out.append(ad)
    return out
