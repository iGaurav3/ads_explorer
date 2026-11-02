from adapters.google import GoogleAdapter
from adapters.link_only import LinkedInAdapter, PinterestAdapter, SnapchatAdapter, TikTokAdapter, TwitterAdapter
from adapters.meta import MetaAdapter
from adapters.microsoft import MicrosoftAdapter


def build_registry():
    adapters = [LinkedInAdapter(), MetaAdapter(), GoogleAdapter(), MicrosoftAdapter(),
                TikTokAdapter(), PinterestAdapter(), SnapchatAdapter(), TwitterAdapter()]
    return {a.platform: a for a in adapters}
