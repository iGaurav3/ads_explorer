# OpenAds Explorer: public ad-library aggregator

Enter a company and collect its individual ad records from public ad libraries into one table:
S.No. · Ad Platform · Details · URL · Published Date · Author.

**No token or login is needed.** Microsoft is fetched automatically. Meta, LinkedIn and Google block automated clients, so
you open their public library in your own browser and send the page to the app with one click (**Capture from browser**).
The app reads the ads on the page, optionally with a free local LLM (llama3 via Ollama). It never returns fake or sample rows.

## Platform capability matrix

| Platform | How ads are collected | Needs | Coverage |
|---|---|---|---|
| **Meta** (Facebook, Instagram) | **Capture from browser** (no token). Optional: official API with `META_ACCESS_TOKEN` | Nothing | Whatever the public Ad Library shows you, including US commercial ads |
| **LinkedIn** | **Capture from browser** (no token). Not fetched automatically: robots.txt / User Agreement prohibit it | Nothing | Whatever the public Ad Library shows you |
| **Google** (Search, Display, YouTube) | **Capture from browser** (no token). Optional: BigQuery public dataset with `GOOGLE_CLOUD_PROJECT` | Nothing | Whatever the Transparency Center shows you |
| **Microsoft / Bing** | Official Ad Library API, fetched automatically | Nothing (unauthenticated) | Ads served in the EU/EEA since June 2023 |
| TikTok, Pinterest, Snapchat, X | Not collected yet | n/a | Link to the public library |

## Capture from browser (no token)

1. Run a search in the app, then drag **⇪ Send to Ads Explorer** from the *Capture from browser* card to your bookmarks bar.
2. Click a platform link in that card. It opens the official library search for your company in a new tab.
3. Scroll until the ads you want have loaded, then click the bookmark. A small window confirms how many ads were added,
   and the table updates. Repeat for each page or platform.

No bookmark? Use *Or paste the page*: paste the page address plus its text (Ctrl+A, Ctrl+C), or upload the page saved
with Ctrl+S. Saved HTML keeps links (ad IDs and landing pages); copied text doesn't.

How it works: the bookmarklet only reads the page that is open in your browser. It sends the visible text to
`127.0.0.1` with `postMessage`, and the server checks the page URL is an official library page. Rules split the page
into one record per ad, using the ad's public ID (Meta Library ID, LinkedIn and Google detail links). The local LLM then
fills in fields the rules missed. **Every LLM value is checked against the page text; anything not found word for word
is discarded**, and missing fields show "Not disclosed". A capture covers only the ads loaded on that page, so its status
is *Partial*.

### Local LLM (optional, free, offline)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3          # about 4.7 GB, needs about 6 GB free RAM
# smaller machines: ollama pull llama3.2:3b and set OLLAMA_MODEL=llama3.2:3b in .env
```

Without Ollama, capture still works with the built-in rules, and the card shows the LLM as not running.

When a platform can't run, its row shows `access_required` / `unsupported_without_auth` with a setup hint and an
"Open public library ↗" link. **The link is not a fetched record.** `no_results` only means a valid search found nothing.

## Quick start

Requirements: Python 3.10+ and Node 18+.

```bash
python -m venv dev && source dev/bin/activate
pip install -r requirements.txt          # add: -r requirements-google.txt for Google
cp .env.example .env                      # optional credentials, see below
(cd frontend && npm install && npm run build)
python server.py                          # http://127.0.0.1:8765  (PORT=… to change)
```

Frontend development with hot reload: run `python server.py`, then `cd frontend && npm run dev`, and open http://localhost:5173.
The Vite dev server proxies `/api` to port 8765.

The old single-file `index.html` at the project root is no longer served; the React app in `frontend/` replaces it.

## Optional credentials (free, not required)

### Meta (`META_ACCESS_TOKEN`)
1. Confirm your identity at https://www.facebook.com/ID.
2. Create an app at https://developers.facebook.com/apps.
3. In the Graph API Explorer, generate a user access token for the app, then exchange it for a long-lived token (about 60 days).
4. Put it in `.env` as `META_ACCESS_TOKEN=...`.

The token is sent only in the `Authorization` header to `graph.facebook.com`. It is never logged, stored, or returned to the
browser. `ad_snapshot_url` is not requested because it embeds the token. Each ad links to its public page
`https://www.facebook.com/ads/library/?id=<id>`.

Keyword search also matches ads that *mention* the company. Results are therefore filtered to Pages whose name matches the
company, and the number excluded is shown. For an exact advertiser search, enter the Meta Page ID under *Advanced*.

### Google (`GOOGLE_CLOUD_PROJECT`)
Google publishes the Transparency Center data under its
[terms](https://adstransparency.google.com/terms), both as a free download (about 170 GB of JSON, refreshed daily, too large
to download per search) and as the BigQuery public dataset `bigquery-public-data.google_ads_transparency_center`.

1. `pip install -r requirements-google.txt`
2. Create a Google Cloud project. The BigQuery sandbox needs no billing account.
3. `gcloud auth application-default login`
4. Set `GOOGLE_CLOUD_PROJECT=<project-id>` in `.env`.

Every search does a dry run first. A query that would scan more than `GOOGLE_MAX_BYTES_BILLED` (default 10 GB) is refused.
Results are cached for `CACHE_TTL_SECONDS`. The dataset has creative format, dates, regions and a per-ad Transparency Center
link, but **no headline or ad text**, so those cells show "Not disclosed". The Transparency Center website's internal
endpoints are never called.

## Field rules

- **Published Date:** no source publishes an exact publication date, so the column shows the closest disclosed date with
  its label: `(first served)` for Microsoft, `(delivery start)` for Meta, `(first shown)` for Google. If no date is
  disclosed it shows `Not disclosed`. The retrieval time is never used.
- **Author:** the disclosed payer (Microsoft `PaidForByName`, Meta `beneficiary_payers`, Google `ad_funded_by`), otherwise
  the advertiser or Page name.
- **URL:** a per-ad public page only when one is verifiable (Meta, Google). Microsoft exposes none, so the column shows
  `Not disclosed`. Landing pages are stored separately.
- **Duplicates:** removed by platform + ad ID. Ads without an ID are only merged when the whole record is identical.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/ads/fetch` | `{company, domain?, platforms[], country?, start_date?, end_date?, limit_per_platform?, meta_page_ids?, fetch_id?}`. Returns ads plus per-platform statuses. |
| `GET /api/ads` | `fetch_id, platform, q, date_from, date_to, sort (platform\|published\|author\|advertiser\|retrieved), order, page, page_size` |
| `GET /api/ads/{id}` | Full record, including source-specific metadata |
| `GET /api/platforms/status` | Capabilities, plus the latest status (`?fetch_id=` gives live progress) |
| `GET /api/ads/export?format=csv\|json&…filters` | Exports exactly the filtered results |
| `POST /api/capture` | `{page_url, text \| html, fetch_id?, company?, use_llm?}`: adds ads from a captured library page |
| `GET /api/llm/status` | Whether the local LLM is reachable and its model is installed |

Interactive docs: http://127.0.0.1:8765/docs. Data is stored in `data/ads.sqlite3`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use clearly labelled synthetic fixtures (`tests/fixtures`) and mocked HTTP/BigQuery. Production code never imports
them, and a test asserts that a live run with no credentials and no network returns zero ads.

## Known limitations

- The unauthenticated Microsoft API is slow (searches can take over a minute), caps `top` at 24, and rate-limits. Ad
  details (dates, payer) are fetched one ad at a time, for at most `MICROSOFT_MAX_DETAILS` (default 50) ads per search.
- Meta, Microsoft and Google only cover ads shown in Europe (plus political ads for Meta). A company advertising only
  in the US may return `no_results`.
- Captured pages contain only the ads that were loaded, so captured counts are always *Partial*.
- The capture rules follow each library's current page layout. If a platform changes its layout, the local LLM can still
  read the page, and anything it can't ground is dropped rather than guessed.
- TikTok, Pinterest, Snapchat and X are link-only.

## Live verification log

- 2026-10-27: Microsoft API reached. It returned an OData validation error for `top=25` (limit is 24, now fixed), and
  advertiser searches for "Nike" didn't respond within 90 s. A connector run for "Adidas" (120 s timeout, one retry)
  also timed out after 242 s, and the app correctly reported `error`, not `no_results`. No live Microsoft ad
  record has been retrieved yet.
- 2026-10-27: Capture pipeline tested end to end on the running server with synthetic, labelled fixture pages: 2 Meta
  records stored, then removed from the database. Not yet tested on a real Meta, LinkedIn or Google page in a browser.
- 2026-10-27: Real `llama3` (8B, Ollama, CPU) tested on the fixture pages. It fills missing advertiser, headline and
  call-to-action text from the page. Its first run copied UI labels ("View details", "Single image ad") and LinkedIn's
  own links; these are now filtered out. It takes about 35–50 s per ad on this machine, so it is only called for ads
  whose advertiser or text the rules could not find (at most `CAPTURE_LLM_MAX_SEGMENTS`, default 10, per capture).
