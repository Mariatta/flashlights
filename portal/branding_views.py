"""The two generated brand assets: the theme stylesheet and the SVG favicon.

Both URLs carry ``brand.version`` as a query string, so the responses can be
cached for a year and still change the moment the environment does.
"""

from django.conf import settings
from django.http import HttpResponse

ONE_YEAR = "public, max-age=31536000, immutable"


def theme_css(request):
    response = HttpResponse(settings.BRAND.theme_css(), content_type="text/css")
    response["Cache-Control"] = ONE_YEAR
    return response


def favicon_svg(request):
    response = HttpResponse(settings.BRAND.favicon_svg(), content_type="image/svg+xml")
    response["Cache-Control"] = ONE_YEAR
    return response


def brand(request):
    """Context processor: ``brand`` in every template."""
    return {"brand": settings.BRAND}
