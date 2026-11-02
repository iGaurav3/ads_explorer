# Public Ads Explorer — Implementation Plan

Source requirements: [implementation.md](implementation.md). High-level phasing: [phase-implementation.md](phase-implementation.md).
This document turns those into concrete, file-level work against the current codebase.

**Current milestone focus: LinkedIn, Google, and Meta.** Microsoft keeps its existing connector, with a minimal port. TikTok, Pinterest, Snapchat, and X get basic status-only adapters. Snapchat's political-ads dataset is deferred and will be decided later.

---

## 0. The constraint that shapes this milestone

None of the three focus platforms offers a **permitted, unauthenticated** way to fetch ad records:

| Platform | Public web UI | Official programmatic access | Scraping the UI |
|---|---|---|---|
| Meta | facebook.com/ads/library | **Ad Library API** (Graph API `ads_archive`). Free, but needs a developer access token from an identity-verified Facebook account. | Not permitted (Meta terms). |
| Google | adstransparency.google.com | **No Transparency Center API.** Official **BigQuery public dataset** `bigquery-public-data.google_ads_transparency_center`. Free tier, but needs a Google Cloud project and credentials. | The site's internal RPC is an undocumented private API, which the spec forbids. |
| LinkedIn | linkedin.com/ad-library | No documented unauthenticated API. Possibly an approved-access API (to verify in L0). | Prohibited by the LinkedIn User Agreement. |

The spec forbids private Ads Manager credentials, credential bypasses, and scraping where it isn't permitted. So this milestone uses an **optional "bring your own developer credentials" mode**:

- **No credentials configured**: the adapter returns `access_required` with setup instructions and the public search link as a fallback. It never returns `no_results` or fake rows.
- **Credentials configured** (environment variables or a local `.env` file): the adapter fetches real records through the official interface.
- These credentials are developer and data-access credentials, **not** ad-account or Ads Manager access. They are always optional. The app still runs with none, as the spec requires.
- Credentials never reach the browser, logs, error messages, or stored URLs.

> **Expected result:** Meta and Google can return real records once the user sets up free credentials. LinkedIn will most likely stay `access_required` with a deep link unless L0 finds an official API. The README and the UI will say exactly this.

---

## 1. Where the code is today

| File | What it does | Keep / change |
|---|---|---|
| `server.py` (~170 lines) | Stdlib `ThreadingHTTPServer`. Serves `index.html` and `GET /api/microsoft?company=`. | Replace with a FastAPI app. Move the Microsoft logic into `adapters/microsoft.py` as is (minimal port). |
| `index.html` (single file, inline CSS/JS) | Hero search, 8 platform link cards, including the existing LinkedIn `accountOwner` and Meta keyword deep links. Microsoft fetch button, CSV/JSON import, card grid, CSV export. | Keep the style and the `safeURL`, `elt`, and `parseCSV` helpers. Reuse the LinkedIn and Meta deep-link builders as fallback links. Replace the card grid with the results table. |
| `README.md` | Launch with `python server.py`. | Rewrite at the end of the milestone. |
| `dev/` | Python 3.14 venv. | Use it for installs and tests. |

---

## 2. Key decisions

| Decision | Choice | Why |
|---|---|---|
| Language | **Python** | The existing code is Python. The work is limited by network round-trips and rate limits, not CPU. Python has the official Google BigQuery client and mature HTTP and test libraries. |
| Framework | **FastAPI + Uvicorn + httpx**, with Pydantic models. SQLite through stdlib `sqlite3`. | Async routes, path parameters, validation, static files, and `/docs` for free. httpx has a built-in `MockTransport` for tests. `python server.py` still starts the app. |
| Credentials | Optional environment variables, loaded with `python-dotenv` from `.env` (git-ignored): `META_ACCESS_TOKEN`, `GOOGLE_CLOUD_PROJECT` + `GOOGLE_APPLICATION_CREDENTIALS` (or gcloud ADC), and `LINKEDIN_ACCESS_TOKEN` (only if L0 finds an API). | Keeps secrets out of the UI and the repo. Without them, each adapter reports `access_required`. |
| Google client | `google-cloud-bigquery`, installed as an **optional extra** (`requirements-google.txt`). It is imported lazily; if it is missing, the adapter reports `access_required` with an install hint. | Users who don't want Google don't need a heavy dependency. |
| Async model | One shared `httpx.AsyncClient`. The orchestrator runs `asyncio.gather` under a semaphore with per-adapter timeouts. The blocking BigQuery client runs in `asyncio.to_thread`. | This matches the async `fetch_ads` interface in the spec. |
| Live progress | `POST /api/ads/fetch` returns records plus statuses. Each platform's status is written to SQLite as it starts and finishes. The UI polls `GET /api/platforms/status?fetch_id=` every second while the request is in flight. | Gives per-platform progress without a job queue. |
| Table display values | The backend computes each record's `row` (platform label, details, URL, published-date label, author). The UI and CSV export both use it. | "Not disclosed" and the date labels are defined once and tested in Python. |
| Filter, sort, page | Done on the server in one query builder shared by `/api/ads` and `/api/ads/export`. | A filtered export always matches the screen. |
| Frontend | Plain HTML/JS, no build step, in `static/app.js` and `static/styles.css`. | Keeps the current approach. |
| Import | Kept as a separate client-side "Imported (user file)" tab that is never persisted. | Preserves the existing feature without mixing provenance. |
| Fixtures | Kept only in `tests/fixtures/`. The HTTP transport and BigQuery client are injectable. | Live responses can never contain fixture data (spec test #12). |

---

## 3. Target layout

```text
public_ads_explorer/
    server.py                 # FastAPI app + routes; `python server.py` runs uvicorn on 127.0.0.1:8765
    config.py                 # settings from env/.env: DB path, cache TTL, timeouts, credentials (never logged)
    index.html
    static/app.js
    static/styles.css
    adapters/
        __init__.py           # REGISTRY
        base.py               # BaseAdapter, FetchRequest, FetchResult, statuses
        meta.py               # Ad Library API (token mode)
        google.py             # BigQuery Transparency Center dataset (credential mode)
        linkedin.py           # status + fallback link; API mode only if L0 confirms one
        microsoft.py          # minimal port of the existing connector
        tiktok.py pinterest.py snapchat.py twitter.py   # basic status-only adapters
    services/
        ad_fetcher.py         # orchestrator
        normalizer.py         # NormalizedAd, to_table_row(), date/author rules
        company_resolver.py   # advertiser-name matching
        deduplicator.py
        validation.py         # input, domain, URL validation; secret redaction
        http_client.py        # httpx wrapper: timeouts, backoff, host allow-list
    database/
        models.py
        storage.py
    tests/
        fixtures/meta/        # ads_archive pages, error 190, error 613, error 10
        fixtures/google/      # BigQuery row dicts, dry-run byte estimates
        test_*.py
    data/                     # SQLite DB (git-ignored)
    .env.example              # documented variable names only, no values
    requirements.txt          # fastapi, uvicorn, httpx, python-dotenv
    requirements-google.txt   # google-cloud-bigquery
    requirements-dev.txt      # pytest, pytest-asyncio
    README.md
```

---

## 4. Shared contracts

### 4.1 Adapter interface

```python
@dataclass
class FetchRequest:
    company_name: str
    company_domain: str | None
    country: str | None          # ISO-3166 alpha-2
    start_date: date | None
    end_date: date | None
    limit: int                   # 1..500, default 100

@dataclass
class FetchResult:
    platform: str
    status: Literal["success","no_results","partial_results","access_required",
                    "unsupported_without_auth","rate_limited","blocked","error"]
    ads: list[NormalizedAd]
    coverage: str
    warnings: list[str]
    error: str | None            # short, secret-redacted
    setup_hint: str | None       # e.g. "Set META_ACCESS_TOKEN — see README §Meta"
    fallback_url: str | None     # public search page; never shown as a record
    started_at: datetime
    finished_at: datetime

class BaseAdapter:
    platform: str
    display_name: str
    requires_credentials: bool
    def is_configured(self) -> bool: ...
    async def fetch_ads(self, req: FetchRequest) -> FetchResult: ...
```

Status rules:
- `no_results` only when a valid, authorised search completed and nothing matched.
- When credentials are missing, return `access_required` immediately, with no network call.
- Invalid or expired credentials also give `access_required`, and are never retried.
- `rate_limited` and `blocked` are distinct statuses.

### 4.2 Normalized record and display rules

These are the spec §6 fields plus `id`, `dedupe_key`, and `source_metadata` (a JSON object of unmapped source fields).

- `published_date` is set only when the source gives an explicit publish date. None of the three focus platforms does. Delivery-start or first-shown dates go to `first_seen`, with `date_type` set to `delivery_start` or `first_shown`.
- `published_date_label` = `"YYYY-MM-DD (delivery start)"`, `"YYYY-MM-DD (first shown)"`, or `"Not disclosed"`. `retrieved_at` is never used.
- `author` = the payer or "paid for by" value when disclosed, else the advertiser or page name, else "Not disclosed".
- `ad_url` = a per-ad public library URL only when it is built from a source-provided ID using a verified URL pattern (see each adapter). It is never a homepage and never contains a token.

### 4.3 Dedupe and storage

- Records are unique on `(platform, ad_id)`. If an ID is missing, the fallback key is the sha256 of the canonical raw record.
- SQLite tables: `ads`, `fetches`, `fetch_platforms`, `fetch_ads`.
- Successful fetches are cached per `(platform, params_hash)`. The TTL is 1 h by default and **24 h for Google**, because every query has a cost. Failures are never cached.

---

## 5. Focus adapters

### 5.1 Meta: `adapters/meta.py` (Ad Library API, token mode)

**L0 verification** (official docs at developers.facebook.com/docs/graph-api/reference/ads_archive and facebook.com/ads/library/api):
- current Graph API version
- required parameters
- available fields
- the coverage rule: non-political ads are only returned for ads delivered in the EU/UK
- rate limits
- the public per-ad URL pattern (expected `https://www.facebook.com/ads/library/?id=<ad_id>`)

**Request:** `GET https://graph.facebook.com/<version>/ads_archive` with these parameters:
- `search_terms=<company>` and `search_type=KEYWORD_UNORDERED`
- `ad_type=ALL` and `ad_active_status=ALL`
- `ad_reached_countries=[<country>]`. If no country is chosen, use the EU/EEA list and add a coverage note.
- `ad_delivery_date_min` / `ad_delivery_date_max` from the date range
- `publisher_platforms` set to Facebook and Instagram
- `fields=id,page_id,page_name,bylines,ad_creative_bodies,ad_creative_link_titles,ad_creative_link_descriptions,ad_creative_link_captions,ad_delivery_start_time,ad_delivery_stop_time,publisher_platforms,languages,eu_total_reach`
- `limit=min(100, remaining)`

The token is sent in the `Authorization` header, not the URL. Paging follows `paging.cursors.after` until `limit` is reached.

**Company matching:**
- `search_terms` matches ad text, not the advertiser. After fetching, keep ads whose `page_name` matches the company (case-folded exact, then contains). Report how many were dropped in `warnings`.
- An optional advanced input, **Meta Page ID**, switches to `search_page_ids` for exact advertiser matching.
- If a domain is given, also keep ads whose `ad_creative_link_captions` host matches it.

**Field mapping:**

| Source | Normalized |
|---|---|
| `id` | `ad_id`. `ad_url` = verified library URL pattern built from the id. |
| `page_name` | `advertiser_name` |
| `bylines`, then `page_name` | `author` |
| `ad_creative_link_titles[0]` | `headline` (the other variations go to `source_metadata`) |
| `ad_creative_bodies[0]` | `ad_copy` |
| `ad_creative_link_descriptions[0]` | `description` |
| `ad_creative_link_captions[0]` | `source_metadata.display_url` (landing URL not exposed, so `landing_page_url` is null) |
| `ad_delivery_start_time` / `ad_delivery_stop_time` | `first_seen` (`date_type=delivery_start`) / `last_seen`. `ad_status` is active when there is no stop time. |
| `publisher_platforms`, `languages`, `eu_total_reach`, `page_id` | `source_metadata` (shown in the details modal) |
| `ad_snapshot_url` | **Not requested and not stored**, because it embeds the access token. |

`creative_type` is null because the API doesn't expose it. The UI shows "Not disclosed".

**Error mapping** (Graph API `error.code`):
- `190` (invalid or expired token), or `10` / `200` (permission, identity not confirmed) → `access_required`, with a setup hint
- `4` / `17` / `613` (throttling) → `rate_limited`, retried once after a backoff
- 5xx / timeout → up to 3 retries with exponential backoff, then `error`
- All error text passes through `redact_secrets()` first.

**User setup (README §Meta):**
1. Confirm your identity at facebook.com/ID.
2. Create a developer app.
3. Generate a user token, then exchange it for a long-lived (about 60-day) token.
4. Put it in `.env` as `META_ACCESS_TOKEN`.

The UI shows the token's expiry if the API reports it.

**Fallback link:** reuse the existing keyword deep link from `index.html`.

### 5.2 Google: `adapters/google.py` (BigQuery public dataset, credential mode)

**L0 verification** (Google Cloud Marketplace listing for "Google Ads Transparency Center" and the dataset schema):
- table names (expected `creative_stats`, and whether a removed-creatives table exists)
- columns: `advertiser_id`, `advertiser_disclosed_name`, `advertiser_legal_name`, `advertiser_location`, `creative_id`, `creative_format`, `creative_page_url`, `region_stats` (repeated: `region_code`, `first_shown`, `last_shown`, serving stats by surface), and topic fields
- coverage (which regions and ad types are included)
- table size, partitioning, and clustering, which drive query cost

**Query** (parameterised, selecting only the columns needed):
```sql
SELECT advertiser_id, advertiser_disclosed_name, advertiser_legal_name, creative_id,
       creative_format, creative_page_url, r.region_code, r.first_shown, r.last_shown,
       r.surface_serving_stats
FROM `bigquery-public-data.google_ads_transparency_center.creative_stats`, UNNEST(region_stats) r
WHERE LOWER(advertiser_disclosed_name) LIKE @name_pattern
  AND (@country IS NULL OR r.region_code = @country)
  AND (@start IS NULL OR r.last_shown >= @start)
  AND (@end IS NULL OR r.first_shown <= @end)
LIMIT @limit_rows
```
The final schema comes from L0. Rows are grouped by `creative_id` in Python, so each creative becomes one record with its per-region dates in `source_metadata`.

**Cost guard (required):**
- Run a **dry run** first.
- If the estimated bytes exceed `GOOGLE_MAX_BYTES_BILLED` (default 10 GB), stop and return `error` with the message *"Query would scan X GB; raise GOOGLE_MAX_BYTES_BILLED to allow."*
- Always set `maximum_bytes_billed` on the real job.
- Cache results for 24 h.

**Field mapping:**

| Source | Normalized |
|---|---|
| `creative_id` | `ad_id` |
| `creative_page_url` | `ad_url` (a per-creative public page on adstransparency.google.com, validated as https on that host) |
| `advertiser_disclosed_name` | `advertiser_name` and `author` (legal name goes to `source_metadata`) |
| `creative_format` (TEXT / IMAGE / VIDEO) | `creative_type`, lower-cased |
| min `first_shown` / max `last_shown` over the matched regions | `first_seen` (`date_type=first_shown`) / `last_seen` |
| Surfaces (Search, YouTube, Display, …) | `source_metadata.surfaces`, shown in Details |
| Headline and copy | **Not in the dataset** → "Not disclosed". The Details column links to the creative page instead. |

**Errors:**
- library missing, or no project or credentials → `access_required` with a setup hint
- `Forbidden` → `access_required`
- `TooManyRequests` / quota exceeded → `rate_limited`
- other errors → `error`

**Domain:** the dataset has no landing-domain column. The domain is ignored for Google, with a warning.

**User setup (README §Google):**
1. Create a Google Cloud project and enable BigQuery (the free tier includes 1 TiB of queries a month).
2. Run `gcloud auth application-default login`, or use a service-account JSON file.
3. Set `GOOGLE_CLOUD_PROJECT`.
4. Run `pip install -r requirements-google.txt`.

**Fallback link:** `https://adstransparency.google.com/?region=<country>`. The UI copies the company name to the clipboard, as it does today.

### 5.3 LinkedIn: `adapters/linkedin.py`

**L0 verification is decisive here.** Check:
- LinkedIn's Ad Library help pages and the LinkedIn developer docs for any official Ad Library or transparency API, including access conditions (for example DSA researcher access) and whether an approved token can be self-served
- the per-ad URL pattern (expected `https://www.linkedin.com/ad-library/detail/<id>`)
- the search URL parameters (`accountOwner`, `countries`, date options)

The Marketing/Advertising API is **not** used. It only serves the caller's own ad accounts.

- **Branch A, official API found and obtainable:** implement token mode like Meta (`LINKEDIN_ACCESS_TOKEN`, header auth, paging, error mapping). Map:
  - advertiser → `advertiser_name`
  - "paid for by" → `author`
  - ad text → `ad_copy`
  - format → `creative_type`
  - first/last impression dates → `first_seen`/`last_seen`
  - the detail URL → `ad_url`
- **Branch B, no obtainable API (most likely):** the adapter returns `access_required` with the coverage note *"LinkedIn does not offer automated access to its Ad Library without approval; use the search link."* It makes no network calls. The fallback deep link is improved: the existing `accountOwner` link plus country and date parameters, if L0 confirms them.

The UI shows the fallback as an "Open LinkedIn Ad Library ↗" button in the platform status panel, never as a table row.

### 5.4 Non-focus adapters (basic for now)

- **Microsoft:** move `search_microsoft` and `normalize_ad` behind the adapter interface with only the changes the contract requires:
  - set `ad_url = null` instead of the homepage
  - return `error` instead of `ok` when every call failed
  - map the rate-limit status

  Detail expansion, pagination, and the other improvements from the earlier plan come in the next milestone.
- **TikTok, Pinterest, Snapchat, X:** status-only adapters that return `access_required` or `unsupported_without_auth`, with a coverage note and a fallback link. They make no network calls. Snapchat's dataset adapter is **deferred**.

---

## 6. HTTP API (`server.py`)

| Endpoint | Behaviour |
|---|---|
| `POST /api/ads/fetch` | The spec §7 body plus optional `fetch_id` and `meta_page_id`. Platform IDs are allow-listed. Returns `{fetch_id, ads[], platforms{}}`. |
| `GET /api/ads` | Filters: `fetch_id`, `platform`, `q`, `date_from`, `date_to`, `sort`, `order`, `page`, `page_size`. |
| `GET /api/ads/{id}` | Full record, including `source_metadata`. |
| `GET /api/platforms/status` | Per platform: `configured`, `requires_credentials`, `setup_hint`, last status. With `?fetch_id=`, live statuses for that run. **Never returns secret values.** |
| `GET /api/ads/export?format=csv\|json&…filters` | Same query builder. CSV values are protected against formula injection. |
| `GET /`, `/static/*` | Frontend files. |

---

## 7. Frontend changes

- **Search form:**
  - company, domain, country, start and end dates, limit
  - optional *Advanced → Meta Page ID*
  - 8 platform checkboxes (LinkedIn, Meta, Google, Microsoft checked by default) with Select all / Deselect all
  - **Fetch Ads** button
- **Badges:** each checkbox shows a badge from `/api/platforms/status`: **Ready**, **Needs setup** (with a tooltip naming the env var), or **Link only**.
- **Status panel:**
  - one row per selected platform: spinner, then a status pill, record count, retrieval time, and the coverage/error message
  - for `access_required`, the setup hint and the fallback "Open public library ↗" button
  - the Google row shows "cached" and the bytes scanned
- **Results table:** columns `S.No. | Ad Platform | Details | URL | Published Date | Author`. Row numbers are recalculated after filtering and sorting. The toolbar has search, platform and date filters, sortable headers, and pagination. Each row has Copy URL and Open ↗ when `ad_url` exists, and "Not disclosed" otherwise.
- **Details modal:** all fields plus `source_metadata`, including Meta's publisher platforms and reach and Google's surfaces and per-region dates.
- **Export:** CSV, JSON, and filtered export.
- **Imported tab:** unchanged.
- **Rendering:** source text is always set with `textContent`, and links go through `safeURL()`.

---

## 8. Security

- Secrets come only from the environment or `.env`. They are never returned by the API, written to the DB, logged, or included in URLs. Meta's token goes in the `Authorization` header. `ad_snapshot_url` is never requested.
- `redact_secrets()` runs on every error string before it is stored or returned.
- Outbound host allow-list: `graph.facebook.com` for Meta, Google APIs through the official client only, and the Microsoft API host. Redirects are rejected.
- The domain input is never fetched; it is only validated and string-matched.
- BigQuery queries are parameterised, with the bytes-billed cap. SQL against SQLite is parameterised, and sort columns come from an allow-list.
- The server is bound to `127.0.0.1`.

---

## 9. Tests

| Spec # | Test |
|---|---|
| 1, 2 | Orchestrator with spy adapters: selecting `["linkedin"]` calls only LinkedIn, and `["meta","google"]` calls exactly those two. |
| 5, 6 | Normalizer: Meta delivery start maps to `first_seen` with no `published_date`. Google first shown is labelled "(first shown)". Author is bylines, then page_name, then Not disclosed. |
| 7, 8 | API: N fixture ads give N rows. Missing headline or creative type gives "Not disclosed". |
| 9 | Dedupe: the same Meta id across pages merges. Google rows for the same `creative_id` across regions become one record. Same copy with different ids stays separate. |
| 10 | Mixed run: Meta fixture succeeds, Google raises, LinkedIn returns `access_required`, and Meta's records still come back with independent statuses. |
| 11 | CSV and JSON exports match the stored records and respect filters. |
| 12 | No credentials, network stubbed to fail: zero ads, and the three focus platforms report `access_required` or `error`, never `no_results`. |
| Meta | Paging through cursors, page_name filtering, Page ID mode, error codes 190/10/613 mapped to the right statuses, no retry on 190, and the token appears in no output (asserted by searching for the token string). |
| Google | Fake BigQuery client: row grouping, field mapping, dry run over the cap gives `error` without running the real query, missing library or credentials gives `access_required`, and the cache is hit on the second call. |
| LinkedIn | Branch B: makes no network calls, returns `access_required`, and the fallback URL is correctly encoded. Branch A tests are added only if that branch is built. |
| Live (opt-in) | `LIVE=1` with real credentials runs one smoke test each for Meta and Google, skipped otherwise. Results are recorded in the README with the date. |

Tools: pytest, FastAPI `TestClient`, `httpx.MockTransport`, and a fake BigQuery client injected via `app.dependency_overrides`.

---

## 10. Milestones

### Current milestone: LinkedIn, Google, Meta

| Step | Work | Done when |
|---|---|---|
| L0 | Verify the Meta, Google, and LinkedIn docs and terms (§5.1–5.3). Decide LinkedIn Branch A or B. Record real sample responses as fixtures where credentials allow. | Every assumption in §5 is confirmed or corrected, with doc links in the README draft |
| L1 | FastAPI skeleton, `config.py` + `.env`, contracts (§4), storage, orchestrator, status-only adapters, minimal Microsoft port | Tests 1, 2, 9, 10, 12 pass; `python server.py` serves the old UI |
| L2 | Meta adapter | Meta tests pass; live smoke test run if a token is available |
| L3 | Google adapter with the cost guard | Google tests pass; live smoke test run if credentials are available |
| L4 | LinkedIn adapter (Branch A or B) | LinkedIn tests pass |
| L5 | API endpoints + export | Tests 7, 8, 11 pass |
| L6 | Frontend (§7) | Manual browser check of each status state (Ready, Needs setup, error) at desktop and 375 px width |
| L7 | README: setup per platform, capability matrix, limitations, test results | Checklist below is ticked |

### Later milestones (not in scope now)

- **Microsoft full upgrade:** detail expansion, pagination, rate-limit backoff, recorded fixtures.
- **Snapchat:** decide on the political-ads dataset adapter.
- **TikTok, Pinterest, X:** re-verify access options.

---

## 11. Milestone acceptance checklist

- [ ] Meta returns real records through the official Ad Library API when `META_ACCESS_TOKEN` is set, and `access_required` with a setup hint when it isn't
- [ ] Google returns real records from the official BigQuery dataset when credentials are set, with the cost guard enforced
- [ ] LinkedIn's status is backed by a verified doc link, and its fallback link is never shown as a record
- [ ] Checkboxes control which adapters run, and every platform reports its own status
- [ ] The six columns appear in order, with "Not disclosed" where a source is silent and no invented dates, authors, or URLs
- [ ] No secrets appear in API responses, the DB, logs, or URLs
- [ ] CSV, JSON, and filtered export all work
- [ ] The README states plainly which platforms need credentials and which are link-only

## 12. Risks and open questions

- **Meta coverage:** non-political ads only come back for EU/UK delivery. A US-only brand will return `no_results` for Meta even with a valid token. The status message must explain this.
- **Meta matching:** keyword search returns ads that *mention* the brand. Page-name filtering reduces noise but can drop sub-brand pages, so the Page ID option is the precise route.
- **Google cost:** the table is large. Name filtering without clustering can scan many GB, so the dry-run cap is mandatory. L0 must measure a typical query's size.
- **Google content:** there is no headline or copy text, so the Details column relies on format, surfaces, dates, and the creative-page link.
- **LinkedIn:** likely link-only for this milestone. If that isn't acceptable, the only compliant route is applying for whatever official access LinkedIn offers, which takes time outside our control.
- **Token expiry:** Meta's long-lived tokens last about 60 days. Expiry gives `access_required` with a clear message, never a silent `no_results`.
