# CODEX PROMPT — Company Advertising Intelligence Dashboard

## Project objective

Upgrade my existing Public Ads Explorer into a fully functional Company Advertising Intelligence Dashboard.

The application must retrieve actual advertisement records from the public ad libraries of Google, LinkedIn and Meta, normalize those records, and generate a data-driven advertising analysis report.

**Do not build a platform link directory. The primary objective is to fetch real advertisement records and calculate metrics from verified collected data.**

Inspect the existing project, implement the functionality directly, run tests and document any unresolved platform-access limitations.

## 1. Mandatory public data sources

**Google Ads Transparency Center**
https://adstransparency.google.com/?region=US

**LinkedIn Ad Library**
https://www.linkedin.com/ad-library

**Meta Ad Library**
https://www.facebook.com/ads/library/

Only use public advertisement data.

Never request a company's private Ads Manager credentials, campaign permissions or billing information.

First investigate each platform's current official API documentation, data export options, permitted collection methods, access requirements and rate limits.

Prioritize official, documented access methods. Optional developer-level credentials can be supported for public transparency APIs, but users must not have to link their advertising accounts.

Do not bypass authentication, anti-bot protections, CAPTCHA, access controls or platform prohibitions on scraping.

Public website access does not automatically imply automated extraction rights.

## 2. Application inputs

Build a responsive input form with the following fields.

**Mandatory:**
- Company Name
- Website URL

**Optional:**
- LinkedIn Company URL

**Countries to analyze:**
- Default: United States (US)
- Multiple countries can be selected.
- Include US, UK, Germany, India, Canada and Australia.
- Support additional countries using ISO 3166-1 alpha-2 codes.
- Use checkboxes or a searchable multi-select component.

**Platform selection:**
- LinkedIn (checked by default)
- Google (checked by default)
- Meta (checked by default)

Add Select All / Deselect All.

**Reporting time period:**
- Last 3 Months
- This Year (YTD)
- Last Year
- Custom Date Range

Define periods precisely:
- Last 3 Months = rolling three calendar months ending today.
- YTD = January 1 of the current year through today.
- Last Year = previous completed calendar year.
- Custom = user-specified inclusive date range.

Use UTC internally and show the effective reporting dates to the user.

Add a primary **Fetch & Analyze Ads** button.

## 3. Company identification

Do not assume the exact company name is identical across advertising libraries.

Build a company resolution service using:
- Company name
- Website domain
- LinkedIn company URL
- Public advertiser or page IDs when available
- Verified brand aliases

Use the company domain as an identity-matching signal.

Allow the user to select or confirm an advertiser when multiple entities match.

Store platform-specific advertiser IDs to make subsequent searches more accurate.

Never merge unrelated advertisers merely because their names look similar.

## 4. Data fetching engine

Create independent connectors:

- GoogleTransparencyConnector
- LinkedInAdLibraryConnector
- MetaAdLibraryConnector

Each connector must:
1. Resolve the advertiser.
2. Validate that retrieval is supported.
3. Apply supported country filters.
4. Apply supported date filters.
5. Retrieve individual ad records.
6. Handle pagination.
7. Normalize the records.
8. Deduplicate advertisements.
9. Save provenance and retrieval timestamps.
10. Return actual records and a structured retrieval status.

Run selected connectors concurrently.

One connector's failure must not prevent the other connectors from completing.

### Google connector

Use the Google Ads Transparency Center as the public reference source.

Retrieve available:
- Advertiser identity
- Ad creative and format
- Ad text when disclosed
- Countries where the ad appeared
- First or last display date when disclosed
- Public creative detail URL
- Landing page URL if disclosed
- Ad platform (Search, Display, YouTube)

Investigate documented regional transparency APIs and datasets.

Do not confuse the Google Ads account-management API with a public competitor-ad API.

If general automated data retrieval is unavailable, return an explicit unsupported/access-limited status.

### LinkedIn connector

Use LinkedIn Ad Library.

Search by company, advertiser, keyword, country and reporting period wherever supported.

Retrieve available:
- Advertiser/company name
- Payer
- Ad creative
- Ad format
- Ad copy
- First and last impression dates
- Public ad detail URL
- Targeted countries or impression geography

Only use methods explicitly permitted by the platform.

Note that LinkedIn's public ad library has historical retention limits and does not necessarily expose the private Campaign Manager's true active/inactive status.

If automatic extraction requires approval or authorization, do not substitute unauthorized scraping.

### Meta connector

Use the Meta Ad Library.

Retrieve available:
- Page ID and page name
- Advertisement/library ID
- Ad creative body and text
- Ad start and end dates
- Active status
- Facebook/Instagram placement
- Public ad snapshot URL
- Country coverage
- Landing page when disclosed

Implement the official Ad Library API when app-level credentials are configured and the requested data is within its supported scope.

Handle the difference between public library browsing and official API coverage.

For ordinary commercial ads, respect the official API's UK/EU coverage limitations.

Never present unavailable US commercial-ad history as zero advertisements.

## 5. Normalized data model

Store individual advertisements with at least these fields:

- id
- platform
- advertiser_name
- advertiser_id
- company_name
- ad_id
- headline
- ad_text
- description
- creative_type
- creative_url
- original_ad_url
- landing_page_url
- first_served_date
- last_served_date
- published_date
- date_type
- active_status (active, inactive, unknown)
- countries
- author_or_payer
- retrieved_at
- source_name
- source_url
- collection_method
- retrieval_coverage
- raw_source_metadata

Use NULL for information the source does not disclose.

Do not invent publication dates, advertiser identities or source URLs.

## 6. Main analytics report

Generate an output dashboard with two columns:

| Metric | Value |
|---|---|
| Company | Actual company name |
| Countries Analyzed | Selected countries |
| Analysis Period | Effective reporting period |
| Active Ads (LinkedIn) | Calculated value or N/A |
| Active Ads (Google) | Calculated value or N/A |
| Active Ads (Meta) | Calculated value or N/A |
| Ads Last 3 Months (LinkedIn) | Calculated count |
| Ads Last 3 Months (Google) | Calculated count |
| Ads Last 3 Months (Meta) | Calculated count |
| Ads This Year (LinkedIn) | Calculated count |
| Ads This Year (Google) | Calculated count |
| Ads This Year (Meta) | Calculated count |
| Ads Last Year (LinkedIn) | Calculated count |
| Ads Last Year (Google) | Calculated count |
| Ads Last Year (Meta) | Calculated count |
| Top Campaign Themes | Top themes inferred from ad content |
| Most Promoted Landing Pages | Top five URLs |
| Competitive Advertising Score | Calculated score and category |

Every metric must be traceable to actual retrieved ad records.

### Important metric rules

**Active Ads**

Count only advertisements explicitly marked active by their source.

Do not interpret a recent impression or an ad's presence in the library as proof that it is currently active.

If active status is unavailable, show N/A.

**Historical Ad Counts**

For each reporting window, count unique advertisements with verified delivery activity overlapping that period, where the source supplies sufficient data.

Do not use the crawler's collection date as the publication date.

Where only partial dates exist, report a suitably labeled observed count instead of inventing delivery intervals.

**Multi-country counting**

An advertisement appearing in the US, UK and Germany should count as one unique creative in the combined report when it is the same platform ad ID.

Retain individual country associations for country-level analysis.

**Data coverage**

Every numerical result must have a coverage label:
- Complete for the supported source scope
- Partial
- Not available

Zero is valid only when an actual successful, sufficiently complete search returned zero matching advertisements.

If only 85 advertisements were retrieved and further pages were unavailable, show at least 85 observed advertisements and mark the count Partial. Do not pretend that 85 is the complete total.

Historical retrieval may need to cover a wider interval than the user's selected primary period because the summary separately includes three-month, YTD and last-year metrics.

Mark each historical window unavailable when outside source retention limits.

## 7. Campaign theme analysis

Analyze actual retrieved advertising copy and available metadata.

Extract campaign themes such as:
- Cloud Security
- AI Operations
- Cybersecurity
- Data Analytics
- Enterprise Automation
- Product Launch
- Discounts and Promotions

Use keyword classification first.

Optionally add an NLP/AI classification module, but it must not require a paid API for the basic application to work.

Return the top five themes with:
- Theme name
- Number of matching advertisements
- Percentage of classified advertisements
- Supporting ad IDs

Do not invent topics for advertisements with inaccessible creative content.

## 8. Most promoted landing pages

Extract disclosed destination URLs.

Normalize URLs by:
- Lowercasing hostnames
- Removing common tracking parameters
- Normalizing trailing slashes
- Preserving meaningful path components

Group advertisements by normalized landing-page URL.

Display the top five landing pages ranked by the number of distinct advertisements linking to each URL.

Include:
- Landing page URL
- Distinct ad count
- Platforms
- Countries

Label this metric "Most Used Landing Pages by Ad Count".

Do not imply that the page received the most impressions or advertising spend, because that information may not be publicly available.

## 9. Competitive Advertising Score

Generate a transparent 0–100 advertising activity score.

Use observed measures including:
- Number of unique advertisements
- Number of platforms with verified activity
- Recency of verified ad activity
- Diversity of advertising themes
- Number of distinct promoted landing pages

Document and show the exact weighting formula.

Suggested display:
- 0–33: Low
- 34–66: Medium
- 67–100: High

These are proposed configurable activity-index bands, not independently validated indicators of competitive strength.

Do not score missing data as zero activity.

If source coverage is inadequate, display "Insufficient Data" instead of generating a misleading score.

If competitor benchmarks are introduced later, provide a separate comparative competitiveness score.

## 10. Detailed advertisements table

Under the summary, display a fully searchable table:

| S.No. | Ad Platform | Details | URL | Published Date | Author |
|---|---|---|---|---|---|

Each row must represent one real, source-verified advertisement.

Include:
- Platform-specific filters
- Country filters
- Date sorting
- Ad copy search
- View Details modal
- Creative preview when permitted
- Open original ad URL
- Pagination

Show "Not Disclosed" for unavailable metadata.

## 11. Platform status dashboard

Create a separate status area:

| Platform | Fetch Status | Records Retrieved | Coverage |
|---|---|---|---|
| LinkedIn | Dynamic | Actual count | Dynamic |
| Google | Dynamic | Actual count | Dynamic |
| Meta | Dynamic | Actual count | Dynamic |

Supported fetch statuses:
- Success
- Partial
- No Results
- Access Required
- Unsupported Without Authentication
- Rate Limited
- Retrieval Error

Provide error explanations and direct public library links where applicable.

No Results must only be shown after a successfully completed search.

Do not insert placeholder advertisement records merely to populate the report.

## 12. Technology and architecture

Preserve the existing project's functioning code where possible.

Recommended technology:

Frontend:
- HTML/CSS/JavaScript or React
- Responsive dashboard
- Company search form
- KPI cards and tables
- Export capabilities

Backend:
- Python FastAPI
- Async HTTP client
- Modular platform connectors
- SQLite for local storage
- Background/parallel fetching
- Caching and structured logging

Proposed endpoints:
- POST /api/analysis/run
- GET /api/analysis/{analysis_id}
- GET /api/analysis/{analysis_id}/summary
- GET /api/analysis/{analysis_id}/ads
- GET /api/analysis/{analysis_id}/coverage
- GET /api/analysis/{analysis_id}/export

Secure all user-supplied URLs to prevent SSRF, sanitize ad content, and handle rate limits.

## 13. Reports and export

Allow exporting:
- Executive Summary as PDF
- Detailed Ads as CSV
- Full Analysis as Excel
- Raw normalized data as JSON

Include in reports:
- Company identity
- Selected countries
- Reporting period
- Retrieval timestamp
- Platform coverage
- Individual advertisement evidence
- Metric definitions
- Incomplete-data warnings

Do not silently remove unsupported platforms from exported results.

## 14. Testing and acceptance criteria

Implement automated tests for:
- Mandatory input validation
- Platform checkbox behavior
- Multi-country selection
- Period calculations
- Advertiser resolution
- Connector response parsing
- Pagination and deduplication
- Active-ad counts
- Historical window counting
- Landing-page normalization
- Theme classification
- Score calculation
- Missing-data handling
- Export generation

Include integration tests using permitted public interfaces and mocked tests using labeled fixtures.

**The project is not complete if it merely generates public library links.**

At least one working live-data retrieval route must be demonstrated using source-verified, individual advertisement records.

For the other mandatory platforms, either implement a permitted retrieval route or visibly explain the precise access blocker.

Do not claim end-to-end success for untested third-party endpoints.

## 15. Final delivery

Deliver:
1. Complete working application code.
2. Updated frontend matching the input and output specifications.
3. Implemented connector modules.
4. Actual-data normalization and analytics.
5. Source coverage and error handling.
6. Export functionality.
7. Test results.
8. Installation and local execution steps.
9. A matrix of which platform/country/period combinations genuinely support automated collection.
10. Documentation of any remaining access approvals.

**Start by inspecting the existing project, then implement the system. Do not stop after producing architecture diagrams or a high-level plan.**
