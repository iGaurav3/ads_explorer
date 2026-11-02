# Public Ads Explorer — Phased Implementation Plan

## Current baseline

The project is a small Python/HTML application. The README describes a standard-library local server, existing public-library links and file import/export, and a best-effort Microsoft Ad Library API connector at `/api/microsoft`. The implementation request expands this into a persisted, normalized multi-platform search application. Preserve working link-based discovery and imports where practical, but keep those features distinct from advertisements actually retrieved by a connector.

## Delivery principles

- Implement the Microsoft Ad Library API as the first fully supported live connector; do not imply that link-only platforms retrieve ads.
- Treat connector status and coverage as first-class results. A failed, restricted, or unsupported connector is not a successful empty search.
- Only display and export records returned by permitted sources. Test fixtures must never enter live results.
- Keep the existing Python and browser-based stack where practical; introduce dependencies only when required by the implementation.
- Complete each phase's exit criteria before building on it. Keep the app runnable at every phase.

## Phase 1 — Baseline inspection and behavior inventory

**Goal:** Identify reusable implementation and settle how new behavior fits the current app before restructuring it.

**Work**

- Inspect `server.py`, `index.html`, and the current README; map routes, UI state, imports/exports, and the Microsoft connector.
- Verify the documented Microsoft endpoints, response shapes, coverage, unauthenticated limits, and permitted use against Microsoft's current official documentation.
- Record which platforms have a permitted unauthenticated retrieval path and which must remain link-only or report unsupported access.
- Identify existing test infrastructure and compatibility constraints.

**Exit criteria**

- Existing behaviors and the Microsoft connector's current capabilities and gaps are documented.
- No connector is represented as live-capable without a verified source and access method.
- A migration approach preserves working features unless they conflict with the new requirements.

## Phase 2 — Shared contracts and normalized record model

**Goal:** Establish one reliable boundary between platform adapters, backend services, storage, and the UI.

**Work**

- Define typed normalized ad records, fetch requests/results, platform statuses, coverage, warnings, errors, and retrieval timestamps.
- Map source fields without inventing publication dates, authors, ad URLs, or other undisclosed values.
- Keep source-specific metadata separate from common fields.
- Define deduplication by platform plus ad ID, with a conservative documented fallback only when an ID is absent.
- Define input validation for platform IDs, dates, result limits, domains, and externally supplied URLs.

**Exit criteria**

- Contract tests cover required/optional fields, null handling, valid status distinctions, and conservative deduplication.
- An absent source value remains absent rather than being replaced with a scrape time or fabricated URL.

## Phase 3 — Microsoft live connector

**Goal:** Deliver the first complete, unauthenticated adapter against Microsoft's documented Ad Library API.

**Work**

- Implement advertiser lookup, ad search with supported pagination, and individual ad-detail retrieval.
- Map advertiser, ad ID, title, description, destination/display URLs, disclosed start/end dates, payer, and relevant metadata.
- Set an original ad URL only when the source provides a verifiable public URL; keep the landing-page destination separate.
- Respect EEA coverage, request timeouts, rate limits, and transient-error retry rules. Do not retry permission/authentication failures.
- Return explicit statuses and coverage explanations for no matches, partial results, limits, and errors.

**Exit criteria**

- Fixture tests verify documented response parsing, detail expansion, dates, advertiser/payer mapping, pagination, and failure/status mapping.
- A live smoke test is attempted when network access permits; its outcome is recorded accurately, including when environmental restrictions prevent verification.
- Connector output contains only actual source data and makes no unsupported URL or publication-date claims.

## Phase 4 — Fetch orchestration, API, and SQLite persistence

**Goal:** Make selected-platform retrieval a stable backend workflow and expose persisted records through the requested API.

**Work**

- Add a platform registry and orchestrator that invokes only selected connectors, runs independent work with bounded concurrency, and preserves successful results if another connector fails.
- Implement `POST /api/ads/fetch`, `GET /api/ads`, `GET /api/ads/{id}`, `GET /api/platforms/status`, and CSV/JSON export endpoints.
- Add SQLite storage for normalized records, provenance, platform status, and retrieval timestamps; enforce duplicate prevention.
- Add configurable successful-response caching and platform-specific pagination/rate-limit handling where supported.
- Ensure export endpoints can export actual normalized results and support the filtered-results workflow required by the UI.
- Apply SSRF protections to any backend network access influenced by user-supplied domains or URLs; do not fetch arbitrary landing pages.

**Exit criteria**

- API tests prove a single-platform request calls only that connector and a multi-platform request calls only selected connectors.
- Mixed success/failure retains successful records and reports each platform's independent status.
- Persistence, retrieval, duplicate handling, and CSV/JSON serialization are tested with fixture data.
- A valid empty search is distinguishable from an unavailable, blocked, rate-limited, or failed search.

## Phase 5 — Dashboard and results workflow

**Goal:** Replace link-only search as the primary results experience with a usable interface to real records and connector outcomes.

**Work**

- Add company, optional domain/country/date fields, configurable per-platform limit, platform checkboxes, and select/deselect-all controls.
- Add a prominent fetch action, per-platform progress/status/count/time/coverage messages, and accessible failure states.
- Render the mandatory table columns in order: S.No., Ad Platform, Details, URL, Published Date, Author. Recalculate row numbers after filtering and sorting.
- Add pagination, sorting, text/platform/date filters, a details view, copy/open-source actions, and CSV/JSON export of filtered records.
- Safely render untrusted source text; validate external links and use clear “Not disclosed” presentation for unavailable display values.
- Keep public-library fallback links and imported user records visibly distinct from connector-fetched records.

**Exit criteria**

- Browser-level or equivalent UI tests confirm the required fields, selected-platform behavior, statuses, one-row-per-ad rendering, details, and filtered exports.
- Empty states and connector failures do not show sample ads or suggest that a link is a fetched ad.
- The UI remains responsive at narrow viewport sizes and existing useful flows remain available.

## Phase 6 — Capability assessment and additional platform adapters

**Goal:** Expand retrieval only where a current, documented, permitted unauthenticated source can return actual records.

**Work**

- Reassess LinkedIn, Meta, Google, TikTok, Pinterest, Snapchat, and X against official documentation and access conditions.
- Implement adapters only for sources that meet the permitted-access requirement, using the shared contract and platform-specific coverage/status reporting.
- For sources requiring credentials, approval, or unsupported automated access, provide an explicit unsupported/access-required status and retain the official public search link as a separate fallback.
- Maintain a capability matrix distinguishing live record retrieval, geographic/date coverage, authentication requirements, and link-only support.

**Exit criteria**

- Every advertised adapter has source-specific tests and documented coverage.
- Unsupported connectors never return fabricated records or success-shaped empty results.
- Platform selection consistently controls which adapters execute.

## Phase 7 — End-to-end verification, security, and documentation

**Goal:** Validate the acceptance criteria across the whole app and leave accurate operational documentation.

**Work**

- Run focused automated tests for connector selection, Microsoft parsing/details/dates/authorship, normalization, deduplication, partial failures, UI display, exports, and live-mode exclusion of fixtures.
- Review URL validation, SSRF protections, HTML handling, bounded concurrency, timeouts, retry behavior, persistence, and cache behavior.
- Run the app locally and perform an end-to-end search; attempt the Microsoft live smoke test if network access is available.
- Update README installation/launch instructions, API usage, storage/cache behavior, testing commands, capability matrix, source limitations, and live-smoke-test outcome.

**Exit criteria**

- All relevant tests and the build/type checks available in the repository pass; any environmental blocker is reported rather than hidden.
- The app provides at least one end-to-end tested live connector, working CSV and JSON exports, and no demo records in live operation.
- Documentation accurately distinguishes verified live retrieval from unsupported connectors, imported records, and fixture-only examples.

## Cross-phase acceptance checklist

- [ ] Actual backend retrieval is the primary results path; platform links alone do not satisfy the requirement.
- [ ] Only selected platforms are invoked, with independent status and failure handling.
- [ ] The six mandatory columns appear in the specified order and contain no fabricated values.
- [ ] Ad URLs are source-verified; landing-page URLs remain separate.
- [ ] SQLite persistence, conservative deduplication, and provenance are in place.
- [ ] Search, sort, filtering, details, pagination, and filtered CSV/JSON exports operate on actual records.
- [ ] Unsupported or access-restricted sources are clearly labeled rather than reported as “no results.”
- [ ] Tests never leak fixture advertisements into live responses or the normal live interface.
- [ ] Installation, operation, capabilities, limitations, and verification results are documented.
