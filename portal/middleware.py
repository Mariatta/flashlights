"""Feature switches enforced at the URL level.

A switched-off feature is not merely unlinked: its pages answer 404, so a
bookmarked or guessed address does not reach a hub the instance does not run.
The switches themselves are settings read from the environment at boot
(``portal/settings.py``, "Feature switches").
"""

from django.conf import settings
from django.http import Http404

#: URL namespace -> the setting that keeps it open.
NAMESPACES = {
    "volunteer": "VOLUNTEERING_ENABLED",
    "sponsorship": "SPONSORSHIP_ENABLED",
}

#: Public stats pages, which share one switch.
STATS_PAGES = {
    "portal_stats",
    "portal_stats_comparison",
    "portal_stats_json",
}


class FeatureSwitchMiddleware:
    """Answer 404 for the pages of a feature that is switched off."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # process_view runs after URL resolution, so the match is always set.
        match = request.resolver_match
        setting = NAMESPACES.get(match.namespace)
        if setting is None and match.url_name in STATS_PAGES:
            setting = "STATS_PUBLIC"
        if setting is not None and not getattr(settings, setting):
            raise Http404(f"{setting} is off on this instance.")
        return None
