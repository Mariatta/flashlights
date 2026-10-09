"""The generated brand assets: the theme stylesheet, the favicons and the
share card.

Every URL carries ``brand.version`` as a query string, so the responses can
be cached for a year and still change the moment the environment does.
"""

from django.conf import settings
from django.http import HttpResponse

ONE_YEAR = "public, max-age=31536000, immutable"


def _asset(body, content_type):
    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = ONE_YEAR
    return response


def theme_css(request):
    return _asset(settings.BRAND.theme_css(), "text/css")


def favicon_svg(request):
    return _asset(settings.BRAND.favicon_svg(), "image/svg+xml")


def favicon_png(request):
    """32px, for browsers that do not take an SVG tab icon (Safari)."""
    return _asset(settings.BRAND.favicon_png(32), "image/png")


def apple_touch_icon(request):
    """180px, the iOS home-screen icon."""
    return _asset(settings.BRAND.favicon_png(180), "image/png")


def share_card(request):
    """The Open Graph image when the instance sets none of its own."""
    return _asset(settings.BRAND.share_card_png(), "image/png")


def brand(request):
    """Context processor: ``brand`` in every template."""
    return {"brand": settings.BRAND}
