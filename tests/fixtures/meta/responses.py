"""TEST FIXTURES ONLY. Shaped after the documented ads_archive / ArchivedAd
response; values are synthetic and never served by the app."""

PAGE_1 = {
    'data': [
        {'id': '9001', 'page_id': '77', 'page_name': 'Fixture Shoes', 'ad_creative_bodies': ['Fixture body one'],
         'ad_creative_link_titles': ['Fixture link title'], 'ad_creative_link_descriptions': ['Fixture link desc'],
         'ad_creative_link_captions': ['fixtureshoes.example'], 'ad_delivery_start_time': '2024-04-01',
         'ad_delivery_stop_time': '2024-04-20', 'publisher_platforms': ['facebook', 'instagram'], 'eu_total_reach': 1200,
         'beneficiary_payers': [{'beneficiary': 'Fixture Shoes', 'payer': 'Fixture Shoes Payer BV', 'current': True}]},
        {'id': '9002', 'page_id': '88', 'page_name': 'Random Sneaker Blog', 'ad_creative_bodies': ['We love Fixture Shoes'],
         'ad_delivery_start_time': '2024-05-01', 'publisher_platforms': ['facebook']},
    ],
    'paging': {'cursors': {'before': 'b1', 'after': 'a1'}, 'next': 'https://graph.facebook.com/v26.0/ads_archive?after=a1'},
}
PAGE_2 = {
    'data': [
        {'id': '9003', 'page_id': '77', 'page_name': 'Fixture Shoes', 'ad_creative_bodies': ['Fixture body three'],
         'publisher_platforms': ['instagram']},
        {'id': '9001', 'page_id': '77', 'page_name': 'Fixture Shoes', 'ad_creative_bodies': ['Fixture body one']},
    ],
    'paging': {'cursors': {'before': 'b2', 'after': 'a2'}},
}

TOKEN_ERROR = {'error': {'message': 'Invalid OAuth access token - Cannot parse access token SECRET-TOKEN-123', 'type': 'OAuthException', 'code': 190}}
RATE_ERROR = {'error': {'message': 'Application request limit reached', 'type': 'OAuthException', 'code': 613}}
