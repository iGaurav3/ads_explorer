# Migration Plan: Public Ads Explorer → Company Advertising Intelligence Dashboard

Source spec: `implementation.md` (revised 2026-10-27). This plan maps the current code base onto the new spec, step by step.
It replaces `IMPLEMENTATION_PLAN.md` for this work.

> **Update 2026-10-27: tokenless collection.** You chose not to use tokens. Meta, LinkedIn and Google are now collected with
> **Capture from browser**: you open the official library and click a bookmarklet; rules plus a local llama3 (Ollama) read
> the page, and every value is grounded against the page text. This is built (`services/capture/`, `POST /api/capture`).
> Where this plan says a platform "needs a token" or "access required", read it as "captured, coverage Partial".
> Captured pages show US commercial ads, so the §2 "Not available for US" limits apply only to the optional API routes.
> The M8 live demo is a real capture in your browser, not an API run.

## 0. What changes, in one paragraph

Today the app fetches ads for one company and shows them in a six-column table. The new spec keeps that table and adds:

- a **company resolution** step with advertiser confirmation
- **multi-country** search and **reporting periods**
- a richer **normalized model** with active status, first/last dates, countries and provenance
- an **analytics report**: active counts, 3-month/YTD/last-year counts, themes, landing pages, an activity score, all with coverage labels
- **PDF/Excel exports** and **analysis-scoped endpoints**

Mandatory platforms are Google, LinkedIn and Meta. Microsoft isn't in the spec. It stays as an optional, off-by-default extra because the spec says to keep working code.

## 1. Gap analysis: current vs. spec

| Spec area | Current state | Gap |
|---|---|---|
| §2 Inputs | Company (required), domain (optional), **single** country, start/end dates, platform checkboxes | Website URL must be **required**; add LinkedIn company URL; multi-country with **US default** and a searchable list; period presets (3M / YTD / Last Year / Custom) with effective UTC dates shown; button renamed **Fetch & Analyze Ads**; defaults are LinkedIn + Google + Meta only |
| §3 Company resolution | Ranking inside each adapter (`match_rank`), no confirmation, nothing stored | New `CompanyResolver` service; candidates per platform; user confirmation when ambiguous; `advertiser_identities` table; domain as a matching signal |
| §4 Connectors | `adapters/{google,meta,microsoft,link_only}.py` follow a common `BaseAdapter` contract | Rename to `*Connector`; split each into resolve → validate → fetch → normalize; pass a country **list**; save provenance; report **truncation** so results can be marked Partial |
| §5 Model | `NormalizedAd` has a single date and no active status, countries list or provenance | Add every §5 field (see §4 below); NULL instead of the "Not disclosed" string in storage |
| §6–9 Analytics | None | New `services/analytics/` package: windows, counts, themes, landing pages, score, coverage |
| §10 Table | Six columns, platform filter, date filters, sorting, paging, details modal, copy URL | Add country filter, ad-copy search on the right field, creative preview (only where permitted), "Not Disclosed" capitalization |
| §11 Status | Per-platform status panel with pills | Change to a table (Platform / Fetch Status / Records / Coverage); align status names (e.g. `partial_results` → **Partial**, `error` → **Retrieval Error**); drop `blocked` (fold into Access Required with a reason) |
| §12 Endpoints | `/api/ads/*`, `/api/platforms/status` | New `/api/analysis/*`; keep the old ones for one milestone, then remove them |
| §13 Exports | CSV and JSON for ads | Add PDF executive summary, an Excel workbook of the full analysis, JSON of the full normalized data; exports include coverage and warnings |
| §14 Tests | 30 tests (adapters, storage, export, isolation) | Add tests for periods, resolution, analytics, themes, score, the new exports and the UI checkbox behavior |

## 2. Platform reality check (it shapes everything else)

| Platform | Permitted retrieval route | Needs | Countries | Active flag | Dates |
|---|---|---|---|---|---|
| **Meta** | Official Ad Library API `ads_archive` | Free developer token (`META_ACCESS_TOKEN`), not the advertiser's account | All ads: EU/UK. Elsewhere, **including US**, only political/issue ads | Yes (`ad_active_status`, delivery stop) | Delivery start/stop |
| **Google** | Official Transparency Center dataset in BigQuery (`bigquery-public-data.google_ads_transparency_center`) | Free GCP project (sandbox) | Coverage of each region **to be re-verified in M0**. The README describes EEA + Turkey from 2023-03 | No (N/A) | `first_shown` / `last_shown` per region |
| **LinkedIn** | **None permitted today.** No public API; robots.txt and the User Agreement prohibit automated access; Cloudflare blocks it | Written permission from LinkedIn (`whitelist-crawl@linkedin.com`), or an approved API program if one exists (to be checked in M0) | n/a | n/a | n/a |
| Microsoft (extra) | Official unauthenticated Ad Library API | Nothing | EU/EEA | No | First served |

Consequences the spec requires us to make visible, never hide:

- **US is the default country, but Meta commercial ads and Google (probably) aren't covered for US.** Those cells must read **Not available (outside API coverage)**, never 0. Meta US political ads can still be counted, labelled "political/issue ads only, Partial".
- **LinkedIn** gets status **Access Required** with the exact blocker text and the public search link. It gets no metrics (N/A), no score credit and no score penalty.
- **The live demo (§14, "at least one working live-data route")** needs a working route. Realistic options, in order:
  1. Meta with a developer token, searching UK/DE/FR for the company.
  2. Google with a GCP project.
  3. Microsoft (tokenless, but it timed out in every live run so far).

  ⚠️ **We need you to provide a Meta token or a GCP project ID for M8.** Without one, we can't honestly claim a working live route.

## 3. Target architecture

```
server.py                         FastAPI app (analysis endpoints + legacy aliases)
config.py                         + countries default, score weights, theme dictionary path
connectors/                       (renamed from adapters/)
  base.py                         Connector contract, ConnectorResult, RetrievalStatus, Coverage
  google_transparency.py          GoogleTransparencyConnector (BigQuery)
  meta_ad_library.py              MetaAdLibraryConnector (ads_archive)
  linkedin_ad_library.py          LinkedInAdLibraryConnector (access-blocked; reports precise blocker)
  microsoft_ad_library.py         optional extra, default off
services/
  periods.py                      ReportingPeriod + window math (UTC)
  company_resolver.py             candidates, scoring, confirmation, identity store
  analysis_runner.py              orchestrates resolve → connectors → normalize → analytics (replaces ad_fetcher.py)
  normalizer.py                   NormalizedAd v2
  url_normalize.py                landing-page normalization
  analytics/
    counts.py                     active + window counts with coverage labels
    themes.py                     keyword classifier (themes.yaml / dict)
    landing_pages.py
    score.py                      Competitive Advertising Score
    report.py                     builds the §6 two-column summary
  exporters/
    csv_export.py, json_export.py, xlsx_export.py (openpyxl), pdf_export.py (fpdf2)
database/storage.py               schema v2 + migrations
frontend/src/
  components/AnalysisForm.jsx     (replaces SearchForm)
  components/AdvertiserConfirm.jsx
  components/SummaryReport.jsx    two-column metric table + KPI cards
  components/StatusTable.jsx      (replaces StatusPanel)
  components/ResultsTable.jsx     (extended)
  components/DetailsModal.jsx     (extended)
```

## 4. Data model v2 (§5)

`NormalizedAd` becomes the following. Fields marked * are new.

| Field | Notes |
|---|---|
| id | DB primary key |
| platform | `google` / `linkedin` / `meta` / `microsoft` |
| advertiser_name, advertiser_id* | from source |
| company_name* | the resolved company this ad was collected for |
| ad_id | platform ad / library / creative ID |
| headline, ad_text (renamed from ad_copy), description* | NULL when not disclosed (Google has no text) |
| creative_type, creative_url* | creative_url only when the source exposes a public creative asset with no token in it. Meta `ad_snapshot_url` embeds the token, so it is not used |
| original_ad_url* | public ad page: Meta `facebook.com/ads/library/?id=`, Google `creative_page_url` (renamed from `ad_url`) |
| landing_page_url | |
| first_served_date*, last_served_date* | from the source only. The old single `first_seen` is split into these two |
| published_date*, date_type | `published_date` = the closest disclosed date (first_served). `date_type` says which one it is |
| active_status* | `active` / `inactive` / `unknown`. Only Meta sets an explicit value |
| countries* | JSON list of ISO-2 codes; also normalized into an `ad_countries` table |
| author_or_payer | renamed from `author` |
| retrieved_at, source_name*, source_url*, collection_method*, retrieval_coverage* | provenance. `collection_method` ∈ `official_api`, `official_dataset`, `user_import` |
| raw_source_metadata | renamed from `source_metadata` |

Storage rules:

- Store NULL. "Not Disclosed" is applied only when rendering a row or an export.
- Dedupe key stays platform + ad_id. A multi-country ad is one row with many `ad_countries` rows (§6, multi-country counting).

### SQLite migration

- Add a `schema_version` table. On startup, `Storage` runs ordered migrations.
- **v1 → v2:** the existing tables hold only cached fetches (no user-owned data), so the migration renames `ads`/`fetches`/`fetch_*` to `legacy_*` and creates the new tables. Old fetches are not converted.
  - New tables: `ads`, `ad_countries`, `analyses`, `analysis_platforms`, `analysis_ads`, `advertiser_identities`, `resolution_candidates`.
- `advertiser_identities(company_key, domain, platform, advertiser_id, advertiser_name, confirmed_by_user, confirmed_at)` lets later runs skip resolution.

## 5. Key logic specs

### 5.1 Periods (`services/periods.py`)

All dates are UTC, with inclusive date ranges.

| Period | Range |
|---|---|
| Last 3 Months | `today − 3 calendar months` (day clamped, e.g. May 31 → Feb 28/29) through today |
| YTD | Jan 1 of the current year through today |
| Last Year | Jan 1 through Dec 31 of the previous year |
| Custom | user-supplied start through end, with start ≤ end and end ≤ today |

- **Primary period** is what the user picked. It drives the table's default filter and the "Analysis Period" row.
- **Fetch window** is the union of the primary period with Last 3 Months, YTD and Last Year, so the report rows can always be computed (§6). The fetch window starts at Jan 1 of last year at the latest.
- A window is marked **Not available** when it falls before the source's retention start: Google 2023-03, Microsoft 2023-06, Meta EU 2023-08 for commercial ads. LinkedIn's retention limit is to be documented.

### 5.2 Company resolution (`services/company_resolver.py`)

1. **Input signals:** name, registrable domain from the website URL (validated; no fetching of the user's URL, so no SSRF), and the LinkedIn company slug. Any stored identities are reused first.
2. **Each connector's `resolve()` returns candidates:** `{advertiser_id, name, evidence}`.
   - Meta: page search via `search_terms`, grouping pages by `page_id`; evidence is a link-caption domain match.
   - Google: SQL `GROUP BY advertiser_id` on name LIKE, plus a check of `creative_page_url` / landing domain.
   - Microsoft: the existing Advertisers search.
3. **Scoring:**
   - exact normalized name = 50
   - alias match = 40
   - domain match in a landing or link URL = +40
   - token prefix match = 20
   - otherwise 0
4. **Outcome:**
   - **Auto-accept** when the top candidate has a domain match and leads the next candidate by 20 or more.
   - **Ambiguous** otherwise: the analysis moves to state `needs_confirmation` and the UI shows `AdvertiserConfirm`. The user can pick one or more candidates, or "none of these".
5. **Never merge by name alone.** Candidates with neither a name nor a domain match are dropped. A multi-select only combines IDs the user explicitly confirmed.
6. **Aliases:** an optional `aliases` field in the form, plus confirmed past identities. No unverified alias lists are invented.

### 5.3 Connector contract (`connectors/base.py`)

```python
async def resolve(ctx) -> list[Candidate]
def supports(ctx) -> SupportCheck        # per-country/period support; precise blocker text
async def fetch(ctx, advertiser_ids) -> ConnectorResult
ConnectorResult(status, ads, coverage: dict[country -> Coverage], truncated: bool,
                pages_fetched, warnings, error, blocker, public_library_url, started_at, finished_at)
```

Status values, matching §11:

| Status | Meaning |
|---|---|
| `success` | Search completed with no truncation |
| `partial` | Truncated by the page/limit cap, or some countries unsupported |
| `no_results` | Only after a completed, untruncated search for supported countries |
| `access_required` | Credentials or approval needed |
| `unsupported_without_auth` | |
| `rate_limited` | |
| `retrieval_error` | |

Coverage per platform × country × window is `complete` / `partial` / `not_available`, plus a reason.

### 5.4 Metrics (`services/analytics/counts.py`)

- **Active Ads:** count of `active_status == 'active'`. For a platform that never reports active status, the value is **N/A**, whatever records exist. Only Meta can be non-N/A.
- **Window counts:** unique (platform, ad_id) where the interval `[first_served, last_served or first_served]` overlaps the window and the ad has a country in the selected set.
  - If only one date is known, the count is labelled **"observed"** and the coverage is at best Partial.
  - If the connector was truncated, the value is shown as `≥ N` and the coverage is Partial.
  - The value is **0** only when the status is `success` and the coverage for that window is complete.
  - Otherwise it is "N/A (reason)".
- **Combined (all-country) counts** count each ad once. A per-country breakdown is kept for the details view and the Excel sheet.
- Every metric object is `{value, display, coverage, reason, supporting_ad_ids}`, so it can be traced (§6).

### 5.5 Themes (`services/analytics/themes.py`)

- A keyword dictionary in `config/themes.json`, editable. The default themes are the seven listed in the spec, each with keyword and phrase lists.
- Matching: case-insensitive, word-boundary matching over headline, ad_text and description. An ad can match several themes.
- Ads with no text are excluded from the denominator and counted as "not classifiable" (e.g. all Google ads).
- Output, top 5: `{theme, ad_count, pct_of_classified, ad_ids}`. An NLP module can be added later; there is no paid API.

### 5.6 Landing pages (`services/url_normalize.py`, `analytics/landing_pages.py`)

- Normalize: lowercase the scheme and host, but keep `www.` (it can be a different site). Also:
  - drop default ports
  - remove `utm_*`, `gclid`, `fbclid`, `msclkid`, `li_fat_id`, `mc_cid`, `mc_eid`, `_hsenc`, `_hsmi`, `ref`, `igshid`
  - sort the remaining query params
  - remove the fragment
  - strip the trailing slash, except for the root path
- Group by distinct ads and take the top 5: `{url, distinct_ad_count, platforms, countries}`.
- Title: "Most Used Landing Pages by Ad Count".

### 5.7 Competitive Advertising Score (`analytics/score.py`)

Shown in the UI and exports with its formula. Weights are configurable.

```
volume     = min(1, log10(1 + unique_ads) / log10(1 + 200))           weight 30
platforms  = active_platforms / evaluable_platforms                    weight 20
recency    = 1 if latest activity ≤ 30 d, linear to 0 at 365 d         weight 20
themes     = min(1, distinct_themes / 5)                               weight 15
landing    = min(1, distinct_landing_pages / 10)                       weight 15
score      = round(Σ weight·component / Σ weight of evaluable components)
```

- **Evaluable platforms** are the platforms with status success/partial and coverage that isn't not_available. LinkedIn, when blocked, is excluded from the denominator, so missing data doesn't count as zero.
- A component with no input data is dropped and its weight redistributed. Example: themes when no ad has text.
- **Insufficient Data** when there are no evaluable platforms, fewer than 5 unique ads, or the evaluable weight is below 50.
- Bands: 0–33 Low, 34–66 Medium, 67–100 High, labelled "activity index, not a validated competitiveness measure".

## 6. API (§12)

| Endpoint | Purpose |
|---|---|
| `POST /api/analysis/run` | `{company_name, website_url, linkedin_url?, aliases?, countries[], platforms[], period: {type, start?, end?}, confirmed_advertisers?}` → `{analysis_id, state}`. The run happens in a background task; state ∈ `resolving`, `needs_confirmation`, `fetching`, `analyzing`, `done`, `failed` |
| `POST /api/analysis/{id}/confirm` | Submit the chosen advertiser IDs per platform and resume (not in the spec's list, but needed for §3) |
| `GET /api/analysis/{id}` | State, inputs, effective dates, candidates, progress |
| `GET /api/analysis/{id}/summary` | The §6 metrics, with coverage |
| `GET /api/analysis/{id}/ads` | Paged, filtered (platform, country, q, date range, sort) |
| `GET /api/analysis/{id}/coverage` | The §11 status table, plus the platform × country × window matrix |
| `GET /api/analysis/{id}/export?format=csv\|json\|xlsx\|pdf` | Exports |

- The frontend polls `GET /api/analysis/{id}` every second, as the live-progress poll does today.
- Legacy `/api/ads/*` stays until M7 and is then removed.
- **Security:**
  - `website_url` and `linkedin_url` are parsed and validated only. They are never fetched.
  - Connector hosts are allow-listed, as `http_client.get_json` already does.
  - Ad text is rendered as text in React (no `dangerouslySetInnerHTML`), and the CSV formula guard is kept.
  - Secrets stay header-only and are redacted.

## 7. Frontend (§2, §6, §10, §11)

- **AnalysisForm**
  - Fields: Company (required), Website URL (required, validated), LinkedIn URL (optional; must be a `linkedin.com/company/...` URL)
  - Countries: a searchable multi-select with US/UK/DE/IN/CA/AU pinned and US preselected; any other ISO-2 code can be added from a full list
  - Platforms: LinkedIn, Google and Meta checked, plus Select All / Deselect All. Microsoft sits under "Additional sources", unchecked
  - Period: radio buttons, and a date range for Custom. Effective UTC dates are shown live
  - Button: **Fetch & Analyze Ads**
- **AdvertiserConfirm:** a candidate list per platform with evidence badges (domain match, exact name), checkboxes, and "None of these".
- **SummaryReport:**
  - KPI cards (unique ads, platforms with activity, score)
  - the two-column Metric/Value table, where every value carries its coverage badge and a tooltip with the reason; clicking a count filters the ads table to its supporting IDs
  - themes and landing-page sub-tables
  - the score formula breakdown
- **StatusTable:** Platform / Fetch Status / Records Retrieved / Coverage, with error explanation and public library link (labelled "not a fetched record").
- **ResultsTable:** existing features, plus a country filter, ad-copy search, and the original-ad link.
- **DetailsModal:** all v2 fields, provenance, and a creative preview. The preview is only an `<img>` of `creative_url` when it is a public asset on an allow-listed host; otherwise "Preview not available, open original ad".
- **Export menu:** PDF summary, CSV ads, Excel full analysis, JSON raw.
- **ImportPanel** stays, but imported rows are tagged `collection_method=user_import` and shown as unverified. They are **excluded from the metrics by default**; a toggle can include them, labelled.

## 8. Exports (§13)

| Format | Library | Contents |
|---|---|---|
| CSV | stdlib (existing) | Ads table, then a header comment block with company, countries, period, retrieval time and coverage warnings |
| JSON | stdlib | `{analysis, inputs, effective_period, coverage, summary, ads[] (full v2 + raw metadata)}` |
| Excel | `openpyxl` | Sheets: Summary, Coverage, Ads, Ad Countries, Themes, Landing Pages, Metric Definitions |
| PDF | `fpdf2` (pure Python) | Executive summary: identity, inputs, metric table with coverage, status table, warnings, definitions, and the top-20 ad evidence list |

- Unsupported platforms appear in every export with their status and reason; they are never dropped silently.
- New dependencies: `openpyxl` and `fpdf2`, added to `requirements.txt`.

## 9. Milestones

| # | Milestone | Main work | Done when |
|---|---|---|---|
| **M0** | Re-verify sources | Re-check the Google BigQuery dataset's region coverage, schema and dry-run cost for one advertiser; whether LinkedIn has any approved Ad Library API or researcher programme; Meta `ad_active_status` and the delivery-date fields. Update `L0-findings.md` | Capability matrix confirmed with sources and dates |
| **M1** | Model + DB migration | NormalizedAd v2, schema_version and the v1→v2 migration, `ad_countries`, analyses tables; adapt the existing connectors' `normalize()` | Existing 30 tests updated and green; new storage tests |
| **M2** | Periods + inputs | `periods.py`; new run body validation (website required, ISO-2 list, period); `POST /run`, `GET /{id}` | Period tests (incl. leap years and month-end), validation tests |
| **M3** | Connectors refactor | Rename to `connectors/`; resolve/supports/fetch split; country lists; truncation flag; LinkedIn blocker connector; Microsoft default off | Mocked parsing, paging and dedupe tests per connector |
| **M4** | Company resolution | Resolver, candidate scoring, identities table, `needs_confirmation` flow, `/confirm` | Resolver tests: exact, alias, domain, ambiguous, unrelated-name rejection |
| **M5** | Analytics | counts, themes, landing pages, score, report builder, `/summary`, `/coverage` | Tests for active N/A, window overlap, ≥N partial, zero-only-when-complete, multi-country dedupe, URL normalization, themes, score and Insufficient Data |
| **M6** | Frontend | Form, confirm step, summary, status table, table/modal upgrades, export menu | `npm run build` passes; component tests (Vitest + Testing Library) for checkbox select/deselect-all, country multi-select and period display |
| **M7** | Exports + cleanup | CSV/JSON/XLSX/PDF, remove legacy endpoints and `ad_fetcher.py`, remove the old root `index.html` (after you confirm) | Export tests open the generated XLSX/PDF and check the contents |
| **M8** | Live verification + docs | Live run on ≥1 route (Meta with your token, or Google with your GCP project; Microsoft if it responds). README: install steps, platform/country/period support matrix, access approvals still needed, test results | One analysis with real, source-verified records, logged in the README with date and counts; nothing untested claimed |

The order is M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8. M6 can start once the M2 API shape is fixed.

## 10. Test plan mapping (§14)

| Spec test | Where |
|---|---|
| Mandatory input validation | `tests/test_api_run.py` |
| Platform checkbox behavior, multi-country selection | `frontend/src/__tests__/AnalysisForm.test.jsx`, plus API validation tests |
| Period calculations | `tests/test_periods.py` |
| Advertiser resolution | `tests/test_resolver.py` |
| Connector parsing, pagination, dedupe | `tests/test_connector_{meta,google,microsoft,linkedin}.py` (labelled fixtures) |
| Active counts, historical windows, missing data | `tests/test_counts.py` |
| Landing-page normalization | `tests/test_url_normalize.py` |
| Theme classification | `tests/test_themes.py` |
| Score | `tests/test_score.py` |
| Exports | `tests/test_exports.py` |
| Integration (live, opt-in) | `tests/live/` marked `@pytest.mark.live`, skipped without credentials or network |

The existing guard tests stay: no fixture imports in production code, no secrets in responses, and zero ads from a no-credential run.

## 11. Decisions needed from you

1. **Live route for M8:** can you provide a Meta developer token, or a GCP project ID for the BigQuery sandbox? Without one, the only tokenless route is Microsoft, which isn't a mandatory platform and has been timing out.
2. **LinkedIn:** OK to ship it as "Access Required" with the precise blocker plus a manual import (excluded from metrics by default)? The alternative is to email LinkedIn for crawl permission. That's your decision and outside the code.
3. **Microsoft:** keep it as an optional extra (my recommendation), or remove it?
4. **Legacy data:** OK to drop the cached v1 fetches in `data/ads.sqlite3` during migration? It is a cache only.
