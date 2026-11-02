"""TEST FIXTURES ONLY: synthetic captured-page text in the bookmarklet's format.

Layouts imitate each library's visible card text; every company, ID, URL and
copy line is invented and must never be shown as real data.
"""

META_URL = ('https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=GB&q=Examplecorp'
            '&search_type=keyword_unordered')
META_TEXT = """Ad Library
Results: ~2
Active
Library ID: 111222333444
Started running on 12 Oct 2025
Platforms
See ad details [[LINK:https://www.facebook.com/ads/library/?id=111222333444]]
Examplecorp [[LINK:https://www.facebook.com/examplecorp]]
Sponsored
Cloud security for every team.
Start a free trial today.
EXAMPLECORP.TEST [[LINK:https://l.facebook.com/l.php?u=https%3A%2F%2Fexamplecorp.test%2Ftrial%3Futm_source%3Dfb&h=x]]
Secure your cloud in minutes
Zero setup required
Learn more
Inactive
Library ID: 555666777888
Oct 1, 2025 - Oct 20, 2025
See ad details
Examplecorp
Sponsored
Our autumn sale ends soon.
Shop now"""

LINKEDIN_URL = 'https://www.linkedin.com/ad-library/search?accountOwner=Examplecorp&countries=US'
LINKEDIN_TEXT = """Ad Library
Examplecorp
Promoted
AI operations that scale with you.
Single image ad
View details [[LINK:https://www.linkedin.com/ad-library/detail/987654321]]
Examplecorp
Promoted
Join our webinar on data analytics.
Video ad
View details [[LINK:https://www.linkedin.com/ad-library/detail/987654322]]"""

LINKEDIN_DETAIL_URL = 'https://www.linkedin.com/ad-library/detail/987654321'
LINKEDIN_DETAIL_TEXT = """Ad details
Examplecorp
Promoted
AI operations that scale with you.
Learn more [[LINK:https://examplecorp.test/aiops]]
Single image ad
Paid for by Examplecorp Holdings Ltd
Ran from Jan 5, 2026 to Mar 1, 2026"""

GOOGLE_URL = 'https://adstransparency.google.com/?region=DE&domain=examplecorp.test'
GOOGLE_TEXT = """Examplecorp
Verified
[[LINK:https://adstransparency.google.com/advertiser/AR01234567890/creative/CR11111111111?region=DE]]
Examplecorp
Verified
[[LINK:https://adstransparency.google.com/advertiser/AR01234567890/creative/CR22222222222?region=DE]]"""

GOOGLE_DETAIL_URL = 'https://adstransparency.google.com/advertiser/AR01234567890/creative/CR11111111111?region=DE'
GOOGLE_DETAIL_TEXT = """Examplecorp
Verified
Format: Text
Last shown: Oct 25, 2025
Shown in Germany
Examplecorp cloud backup - plans from 5 EUR"""

# A Meta card without the "Sponsored" line: rules find the ID and date but not the advertiser or text.
META_VARIANT_TEXT = """Active
Library ID: 222333444555
Started running on 2 Mar 2026
Examplecorp
Data analytics made simple.
Learn more"""

UNANCHORED_URL = 'https://www.linkedin.com/ad-library/search?accountOwner=Examplecorp'
UNANCHORED_TEXT = """Examplecorp
Promoted
Enterprise automation, simplified.
Single image ad
View details"""

META_HTML = """<html><head><title>Ad Library</title><script>var x = "Library ID: 999";</script></head><body>
<div>Active</div><div>Library ID: 123456789012</div><div>Started running on 3 Feb 2026</div>
<div><a href="https://www.facebook.com/examplecorp">Examplecorp</a></div><div>Sponsored</div>
<div>Spring launch &amp; more</div></body></html>"""
