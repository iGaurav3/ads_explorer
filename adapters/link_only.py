"""Platforms without a permitted, automated way to fetch ads.

These adapters never make network calls. They report why records cannot be
fetched and offer the platform's public library as a fallback link, which the
UI shows separately from fetched records.
"""
from urllib.parse import urlencode

from adapters.base import BaseAdapter, FetchRequest, now_iso


class LinkOnlyAdapter(BaseAdapter):
    retrieval = 'link_only'
    status = 'unsupported_without_auth'
    reason = ''
    library_url = ''

    def fallback_url(self, req):
        return self.library_url

    async def fetch_ads(self, req: FetchRequest):
        return self.result(req, self.status, error=self.reason, started_at=now_iso(), finished_at=now_iso())


class LinkedInAdapter(LinkOnlyAdapter):
    platform = 'linkedin'
    display_name = 'LinkedIn'
    coverage = 'LinkedIn Ad Library (public website): ads from the past year; EU ads include targeting details.'
    status = 'access_required'
    reason = ('LinkedIn does not offer an open Ad Library API, and its terms prohibit automated access without '
              'permission, so it is not fetched automatically. Open the public Ad Library below, then click '
              '"Send to Ads Explorer" (Capture from browser) to add the ads you see.')

    def fallback_url(self, req):
        params = {'accountOwner': req.company_name}
        if req.country:
            params['countries'] = req.country
        if req.start_date or req.end_date:
            params['dateOption'] = 'custom-date-range'
            if req.start_date:
                params['startdate'] = req.start_date.isoformat()
            if req.end_date:
                params['enddate'] = req.end_date.isoformat()
        return 'https://www.linkedin.com/ad-library/search?' + urlencode(params)


class TikTokAdapter(LinkOnlyAdapter):
    platform = 'tiktok'
    display_name = 'TikTok'
    coverage = 'TikTok Commercial Content Library: ads shown in the EEA, Switzerland and the UK.'
    status = 'access_required'
    reason = 'The TikTok Commercial Content API requires an approved application.'
    library_url = 'https://library.tiktok.com/ads'


class PinterestAdapter(LinkOnlyAdapter):
    platform = 'pinterest'
    display_name = 'Pinterest'
    coverage = 'Pinterest Ads Repository: ads shown in the EU.'
    reason = 'No open, documented Ads Repository API is available.'
    library_url = 'https://ads.pinterest.com/ads-repository/'


class SnapchatAdapter(LinkOnlyAdapter):
    platform = 'snapchat'
    display_name = 'Snapchat'
    coverage = 'Snapchat Ads Gallery: ads shown in the EU.'
    reason = 'No open Ads Gallery API. (The political-ads dataset is not enabled yet.)'
    library_url = 'https://adsgallery.snap.com/'


class TwitterAdapter(LinkOnlyAdapter):
    platform = 'twitter'
    display_name = 'X / Twitter'
    coverage = 'X Ads Repository: ads shown in the EU.'
    reason = 'No open Ads Repository API is available.'
    library_url = 'https://ads.x.com/ads-repository'
