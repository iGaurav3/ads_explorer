"""TEST FIXTURES ONLY. Shaped after the documented Microsoft Ad Library objects
(Advertiser, Ad, AdDetails); values are synthetic and never served by the app."""

ADVERTISERS = [
    {'AdvertiserId': 1001, 'AdvertiserName': 'Fixture Shoes GmbH', 'AdvertiserCountry': 'DE', 'IsVerified': True},
    {'AdvertiserId': 1002, 'AdvertiserName': 'Unrelated Corp', 'AdvertiserCountry': 'FR', 'IsVerified': False},
]

ADS_PAGE_1 = [
    {'AdId': 501, 'AdvertiserId': 1001, 'AdvertiserName': 'Fixture Shoes GmbH', 'Title': 'Fixture title A',
     'Description': 'Fixture description A', 'DisplayUrl': 'fixtureshoes.example', 'DestinationUrl': 'https://www.fixtureshoes.example/a',
     'AssetJson': None},
    {'AdId': 502, 'AdvertiserId': 1001, 'AdvertiserName': 'Fixture Shoes GmbH', 'Title': 'Fixture title B',
     'Description': 'Fixture description B', 'DisplayUrl': 'fixtureshoes.example', 'DestinationUrl': 'https://shop.fixtureshoes.example/b'},
]
ADS_PAGE_2 = [
    {'AdId': 503, 'AdvertiserId': 1001, 'AdvertiserName': 'Fixture Shoes GmbH', 'Title': 'Fixture title C',
     'Description': 'Fixture description C', 'DisplayUrl': 'other.example', 'DestinationUrl': 'https://other.example/c'},
    # duplicate of 501 returned again by the API
    {'AdId': 501, 'AdvertiserId': 1001, 'AdvertiserName': 'Fixture Shoes GmbH', 'Title': 'Fixture title A',
     'Description': 'Fixture description A', 'DisplayUrl': 'fixtureshoes.example', 'DestinationUrl': 'https://www.fixtureshoes.example/a'},
]

DETAILS = {
    501: {'AdId': 501, 'AdvertiserName': 'Fixture Shoes GmbH', 'AdDetails': {
        'PaidForByName': 'Fixture Payer Ltd', 'StartDate': '2024-02-01T00:00:00Z', 'EndDate': '2024-03-15T00:00:00Z',
        'TotalImpressionsRange': '1K-10K'}},
    502: {'AdId': 502, 'AdvertiserName': 'Fixture Shoes GmbH', 'AdDetails': {
        'StartDate': '2024-05-10T00:00:00Z', 'EndDate': '2024-05-20T00:00:00Z'}},
    503: {'AdId': 503, 'AdvertiserName': 'Fixture Shoes GmbH', 'AdDetails': {}},
}
