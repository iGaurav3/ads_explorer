# L0 Findings: tokenless access check (2026-10-27)

Goal: confirm whether LinkedIn, Meta, and Google public ad libraries can be fetched **without any token or login**.

## Environment

- Node v24.15.0 / npm 12.0.1 (React + Vite is possible)
- Python 3.14.4 in `dev/` venv, no packages installed yet
- Outbound network is available

## Probes (plain HTTPS GET with normal browser headers, no cookies)

| Platform | URL probed | Result | What it means |
|---|---|---|---|
| LinkedIn | `/ad-library/search?accountOwner=Nike` | **403**: Cloudflare "Sorry, you have been blocked" | LinkedIn actively blocks non-browser clients |
| LinkedIn | `/robots.txt` | 200 | States: *"The use of robots or other automated means to access LinkedIn without the express permission of LinkedIn is strictly prohibited."* Points to `whitelist-crawl@linkedin.com` for permission. |
| Meta | `/ads/library/?q=Nike…` | **403**: JavaScript bot-verification challenge page (`__rd_verify_…`) | Meta serves a bot challenge to automated clients; no ad data in the response |
| Google | `adstransparency.google.com/?region=anywhere` | **200**: app shell (~370 KB) | The page loads, but ads are fetched afterwards by the page's internal RPC calls (`/anji/_/rpc/...`), which are not a published API |
| Google | `/robots.txt` | 404 | No robots policy published |

## Blocked step

Calling Google's internal search RPC (`SearchService/SearchSuggestions`) to check whether it answers without a token was **refused by this environment's safety policy**. The reason given was website access circumvention, because it is an undocumented private endpoint. I did not try to get around this.

## Conclusion

No platform among the three offers a tokenless, officially supported way to fetch ads.

- **LinkedIn** and **Meta** actively block automated clients. Getting past that would require bot-detection evasion (stealth browsers, challenge solving, rotating IPs). That is outside what I'll build, and it is explicitly ruled out by `implementation.md` §4.
- **Google**'s data is reachable only through its private internal RPC. Using that is also ruled out by `implementation.md` §4 ("undocumented private APIs"), and this environment blocks it.

## Update: verified interfaces chosen for the build

- **Microsoft Ad Library API** ([docs](https://learn.microsoft.com/en-us/advertising/guides/ad-library-api)): unauthenticated.
  - `Advertisers` and `Ads` take `top`/`skip`/`searchText`. `Ads` also takes `advertiserId`, `startDate`/`endDate` (yyyy-MM-dd) and `countryCodes` (numeric IDs, mapped in code).
  - `AdDetails` is only available per ad, via `Ads/{id}?$expand=AdDetails`.
  - Live checks: `top` > 24 gives an OData 400. Valid searches can take over 90 s.
- **Meta Ad Library API** ([ads_archive](https://developers.facebook.com/docs/graph-api/reference/ads_archive/), [ArchivedAd](https://developers.facebook.com/docs/graph-api/reference/archived-ad/)): v26.0, needs a free token.
  - Error codes: 190 (bad token), 613 (rate limit).
  - `bylines`, spend and impressions are political-only. `beneficiary_payers` and `eu_total_reach` are EU-only.
  - Non-EU results are limited to political/issue ads.
- **Google Ads Transparency Center dataset** ([README](https://storage.googleapis.com/ads-transparency-center/api-data/README.txt)): official, under the Google ToS and the Transparency Center terms.
  - As a direct download it is 999 JSON shards of about 170 MB each (about 171 GB), refreshed daily, so it is impractical per search.
  - The same data is in the BigQuery public dataset (free sandbox).
  - Fields: `creative_id`, `creative_page_url`, `ad_format_type`, `advertiser_disclosed_name`, `ad_funded_by`, `region_stats[].first_shown/last_shown`. There is no ad text.
- **LinkedIn**: public library link and import only.

## Options that work without a token

1. **Microsoft Ad Library API**: official, public, no token. It already works in `server.py`. Covers EU/EEA ads.
2. **Snapchat Political Ads dataset**: official public download, no token (political/advocacy ads only).
3. **Assisted collection for LinkedIn, Meta, and Google**: the app opens the official library search for the company in the user's own browser. The user exports or saves results (or uses the existing CSV/JSON import), and the app normalizes them into the six-column table.
4. **Token-based official APIs** (earlier plan): Meta Ad Library API and Google's BigQuery dataset. Both are free but need one-time credentials.
