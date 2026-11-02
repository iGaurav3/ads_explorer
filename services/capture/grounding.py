"""Keep only values that literally occur in the captured page.

The LLM may only copy text. Anything it returns that cannot be found in the
source segment (case and whitespace aside) is discarded, so a hallucinated
headline, advertiser, ID, URL or date never reaches the table.
"""
import re

from services.capture.page_text import links_in, strip_links
from services.capture.rules import parse_date


def _norm(text):
    return ' '.join(str(text or '').casefold().split())


def grounded_text(value, source):
    value = _norm(value)
    return bool(value) and value in _norm(strip_links(source))


def grounded_link(value, source):
    return bool(value) and str(value).strip() in links_in(source)


def grounded_date(value, source):
    """`value` is the date as written on the page; returns ISO date or None."""
    return parse_date(value) if grounded_text(value, source) else None


TEXT_FIELDS = ('advertiser_name', 'author', 'headline', 'ad_copy', 'description', 'call_to_action', 'creative_type')


def ground(candidate, source):
    """Filter an LLM-proposed dict down to verifiable fields. Returns (fields, dropped_field_names)."""
    out, dropped = {}, []
    for name in TEXT_FIELDS:
        value = candidate.get(name)
        if value in (None, ''):
            continue
        if isinstance(value, str) and grounded_text(value, source):
            out[name] = ' '.join(value.split()) if name != 'ad_copy' else value.strip()
        else:
            dropped.append(name)
    if (value := candidate.get('ad_id')) not in (None, ''):
        value = str(value).strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{4,40}', value) and grounded_text(value, source):
            out['ad_id'] = value
        else:
            dropped.append('ad_id')
    if (value := candidate.get('landing_page_url')) not in (None, ''):
        if grounded_link(value, source):
            out['landing_page_url'] = str(value).strip()
        else:
            dropped.append('landing_page_url')
    for name, key in (('first_seen', 'first_date_text'), ('last_seen', 'last_date_text')):
        if (value := candidate.get(key)) not in (None, ''):
            iso = grounded_date(value, source)
            if iso:
                out[name] = iso
            else:
                dropped.append(name)
    return out, dropped
