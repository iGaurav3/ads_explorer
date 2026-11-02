"""SQLite persistence for normalized ads, fetch runs and per-platform statuses."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sqlite3

from services.normalizer import NormalizedAd, dedupe_key, to_table_row

AD_COLUMNS = [f for f in NormalizedAd.__dataclass_fields__ if f != 'source_metadata']

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY,
    dedupe_key TEXT NOT NULL,
    {', '.join(c + ' TEXT' for c in AD_COLUMNS)},
    source_metadata TEXT NOT NULL DEFAULT '{{}}',
    first_retrieved_at TEXT NOT NULL,
    UNIQUE (platform, dedupe_key)
);
CREATE TABLE IF NOT EXISTS fetches (
    fetch_id TEXT PRIMARY KEY,
    params TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fetch_platforms (
    fetch_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{{}}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (fetch_id, platform)
);
CREATE TABLE IF NOT EXISTS fetch_ads (
    fetch_id TEXT NOT NULL,
    ad_pk INTEGER NOT NULL REFERENCES ads(id),
    platform TEXT NOT NULL,
    PRIMARY KEY (fetch_id, ad_pk)
);
CREATE INDEX IF NOT EXISTS fetch_platforms_cache ON fetch_platforms (platform, params_hash, status);
"""

SORTS = {
    'platform': 'a.platform',
    'published': "COALESCE(a.published_date, a.first_seen)",
    'author': 'COALESCE(a.author, a.advertiser_name)',
    'advertiser': 'a.advertiser_name',
    'retrieved': 'a.retrieved_at',
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def params_hash(platform, params):
    raw = json.dumps({'platform': platform, **params}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class Storage:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript(SCHEMA)

    def _conn(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def create_fetch(self, fetch_id, params, platforms):
        now = utcnow()
        with self._conn() as db:
            db.execute('INSERT OR REPLACE INTO fetches VALUES (?, ?, ?)', (fetch_id, json.dumps(params, default=str), now))
            for platform in platforms:
                db.execute('INSERT OR REPLACE INTO fetch_platforms VALUES (?, ?, ?, ?, ?, ?)',
                           (fetch_id, platform, params_hash(platform, params), 'pending', '{}', now))

    def set_status(self, fetch_id, platform, status, summary=None):
        with self._conn() as db:
            db.execute('UPDATE fetch_platforms SET status = ?, summary = ?, updated_at = ? WHERE fetch_id = ? AND platform = ?',
                       (status, json.dumps(summary or {}, default=str), utcnow(), fetch_id, platform))

    def save_ads(self, fetch_id, ads):
        """Upsert ads (unique per platform + dedupe key) and link them to this fetch. Returns row ids."""
        ids = []
        with self._conn() as db:
            for ad in ads:
                data = ad.to_dict()
                values = [data[c] for c in AD_COLUMNS]
                key = dedupe_key(ad)
                metadata = json.dumps(data['source_metadata'], ensure_ascii=False, default=str)
                db.execute(
                    f"INSERT INTO ads (dedupe_key, {', '.join(AD_COLUMNS)}, source_metadata, first_retrieved_at) "
                    f"VALUES (?, {', '.join('?' * len(AD_COLUMNS))}, ?, ?) "
                    f"ON CONFLICT (platform, dedupe_key) DO UPDATE SET "
                    + ', '.join(f'{c} = excluded.{c}' for c in AD_COLUMNS if c != 'platform')
                    + ', source_metadata = excluded.source_metadata',
                    [key, *values, metadata, data['retrieved_at']])
                pk = db.execute('SELECT id FROM ads WHERE platform = ? AND dedupe_key = ?', (ad.platform, key)).fetchone()[0]
                ids.append(pk)
                db.execute('INSERT OR IGNORE INTO fetch_ads VALUES (?, ?, ?)', (fetch_id, pk, ad.platform))
        return ids

    def record_capture(self, fetch_id, platform, company, page_url, captured, coverage, warnings):
        """Status for a platform filled from user-captured pages; counts every ad captured into this fetch so far."""
        now = utcnow()
        with self._conn() as db:
            db.execute('INSERT OR IGNORE INTO fetches VALUES (?, ?, ?)',
                       (fetch_id, json.dumps({'company': company, 'source': 'user_capture'}), now))
            prev = db.execute('SELECT status, summary FROM fetch_platforms WHERE fetch_id = ? AND platform = ?',
                              (fetch_id, platform)).fetchone()
            total = db.execute('SELECT COUNT(*) FROM fetch_ads WHERE fetch_id = ? AND platform = ?',
                               (fetch_id, platform)).fetchone()[0]
            old = json.loads(prev['summary']) if prev else {}
            pages = [*old.get('captured_pages', []), page_url][-20:] if old.get('source_type') == 'user_capture' else [page_url]
            if total:
                status, error = 'partial_results', None
            else:
                status = 'error'
                error = ('No ads were recognized on the captured page. Make sure the search results are visible '
                         'before capturing, or start the local LLM to read pages the rules do not recognize.')
            summary = {'platform': platform, 'status': status, 'record_count': total, 'coverage': coverage,
                       'warnings': warnings, 'error': error, 'source_type': 'user_capture', 'captured_pages': pages,
                       'last_capture_count': captured, 'fallback_url': old.get('fallback_url'),
                       'started_at': old.get('started_at') or now, 'finished_at': now, 'cached': False}
            db.execute('INSERT OR REPLACE INTO fetch_platforms VALUES (?, ?, ?, ?, ?, ?)',
                       (fetch_id, platform, 'user_capture', status, json.dumps(summary, default=str), now))
        return summary

    def cached(self, platform, params, ttl_seconds):
        """Most recent successful run for identical parameters within the TTL: (summary, [ad ids]) or None."""
        if ttl_seconds <= 0:
            return None
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat(timespec='seconds')
        with self._conn() as db:
            row = db.execute(
                "SELECT fetch_id, summary FROM fetch_platforms WHERE platform = ? AND params_hash = ? "
                "AND status IN ('success', 'no_results') AND updated_at >= ? ORDER BY updated_at DESC LIMIT 1",
                (platform, params_hash(platform, params), cutoff)).fetchone()
            if not row:
                return None
            ids = [r[0] for r in db.execute('SELECT ad_pk FROM fetch_ads WHERE fetch_id = ? AND platform = ?', (row['fetch_id'], platform))]
        return json.loads(row['summary']), ids

    def link_ads(self, fetch_id, platform, ids):
        with self._conn() as db:
            db.executemany('INSERT OR IGNORE INTO fetch_ads VALUES (?, ?, ?)', [(fetch_id, pk, platform) for pk in ids])

    def statuses(self, fetch_id=None):
        with self._conn() as db:
            if fetch_id:
                rows = db.execute('SELECT * FROM fetch_platforms WHERE fetch_id = ?', (fetch_id,)).fetchall()
            else:
                rows = db.execute(
                    'SELECT fp.* FROM fetch_platforms fp JOIN (SELECT platform, MAX(updated_at) AS u FROM fetch_platforms '
                    "WHERE status NOT IN ('pending', 'running') GROUP BY platform) last "
                    'ON fp.platform = last.platform AND fp.updated_at = last.u').fetchall()
        return {r['platform']: {**json.loads(r['summary']), 'status': r['status'], 'updated_at': r['updated_at']} for r in rows}

    def _where(self, filters):
        clauses, args, join = [], [], ''
        if filters.get('fetch_id'):
            join = 'JOIN fetch_ads fa ON fa.ad_pk = a.id'
            clauses.append('fa.fetch_id = ?')
            args.append(filters['fetch_id'])
        if filters.get('platforms'):
            clauses.append(f"a.platform IN ({', '.join('?' * len(filters['platforms']))})")
            args.extend(filters['platforms'])
        if filters.get('q'):
            like = '%' + filters['q'].replace('%', '').replace('_', '') + '%'
            clauses.append('(' + ' OR '.join(f'a.{c} LIKE ?' for c in ('headline', 'ad_copy', 'description', 'advertiser_name', 'author', 'ad_id')) + ')')
            args.extend([like] * 6)
        day = "substr(COALESCE(a.published_date, a.first_seen), 1, 10)"
        if filters.get('date_from'):
            clauses.append(f'{day} >= ?')
            args.append(str(filters['date_from']))
        if filters.get('date_to'):
            clauses.append(f'{day} <= ?')
            args.append(str(filters['date_to']))
        return join, (' WHERE ' + ' AND '.join(clauses)) if clauses else '', args

    def query_ads(self, filters, page=1, page_size=25):
        """Filter/sort/paginate. page_size=None returns every match (exports)."""
        join, where, args = self._where(filters)
        order = SORTS.get(filters.get('sort') or 'platform', SORTS['platform'])
        direction = 'DESC' if filters.get('order') == 'desc' else 'ASC'
        sql = f'SELECT a.* FROM ads a {join}{where} ORDER BY {order} IS NULL, {order} {direction}, a.id'
        with self._conn() as db:
            total = db.execute(f'SELECT COUNT(*) FROM ads a {join}{where}', args).fetchone()[0]
            if page_size:
                sql += ' LIMIT ? OFFSET ?'
                args = [*args, page_size, (max(page, 1) - 1) * page_size]
            else:
                sql += ' LIMIT 10000'
            rows = [self._record(r) for r in db.execute(sql, args)]
        return total, rows

    def get_ad(self, ad_pk):
        with self._conn() as db:
            row = db.execute('SELECT * FROM ads WHERE id = ?', (ad_pk,)).fetchone()
        return self._record(row) if row else None

    @staticmethod
    def _record(row):
        data = dict(row)
        data['source_metadata'] = json.loads(data.get('source_metadata') or '{}')
        data.pop('dedupe_key', None)
        data['row'] = to_table_row(data)
        return data
