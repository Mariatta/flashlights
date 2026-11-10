import math
import time

import bleach
import markdown as markdown_lib
from allauth.account import app_settings as allauth_settings
from allauth.core.internal import ratelimit as allauth_ratelimit
from django import template
from django.conf import settings
from django.core.cache import cache
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def page_title(name):
    """The page's <title>: "Name | short name" for a page that names itself,
    the instance's title alone for one that does not (the landing, and every
    upstream page that sets no name of its own). The instance comes from
    the settings, so a template rendered without the context processors
    is titled the same way."""
    brand = settings.BRAND
    name = " ".join(str(name).split())
    if not name:
        return conditional_escape(brand.title)
    return mark_safe(f"{name} | {conditional_escape(brand.short_name)}")


# Tags/attributes allowed in rendered descriptions. Kept tight since the output
# is shown on public pages; everything else is stripped by bleach.
_MARKDOWN_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "code",
    "pre",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
]
_MARKDOWN_ATTRS = {"a": ["href", "title", "rel"]}


@register.filter
def markdownify(value):
    """Render Markdown to sanitized HTML for display."""
    if not value:
        return ""
    html = markdown_lib.markdown(value, extensions=["extra", "nl2br", "sane_lists"])
    clean = bleach.clean(html, tags=_MARKDOWN_TAGS, attributes=_MARKDOWN_ATTRS)
    return mark_safe(clean)


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get a value from a dictionary by key,
    returning None if not found.
    """
    return dictionary.get(key)


@register.filter
def as_currency(value):
    """
    Template filter to format a number as currency.
    """
    try:
        amount = float(value)
        return f"${amount:,.0f}"
    except (TypeError, ValueError):
        return ""


#: The allauth setting that holds each code page's lifetime, in seconds.
CODE_LIFETIME_SETTINGS = {
    "email_verification": "EMAIL_VERIFICATION_BY_CODE_TIMEOUT",
    "login": "LOGIN_BY_CODE_TIMEOUT",
    "password_reset": "PASSWORD_RESET_BY_CODE_TIMEOUT",
}


@register.simple_tag
def code_lifetime_minutes(flow):
    """How many minutes a code sent for ``flow`` works, from allauth's own
    setting, so the code page's sentence and the expiry allauth enforces
    cannot disagree. Never less than one."""
    seconds = getattr(allauth_settings, CODE_LIFETIME_SETTINGS[flow])
    return max(1, round(seconds / 60))


@register.simple_tag(takes_context=True)
def new_code_wait_seconds(context, email):
    """Whole seconds until allauth will send another verification email to
    ``email``; 0 when it would send one now. Read from allauth's own record
    for its "confirm_email" limit (one email per address every ten seconds
    in code mode), so the code page's countdown and the limit agree and a
    person who waits for it never meets the 429 page."""
    request = context.get("request")
    if request is None or not email:
        return 0
    now = time.time()
    wait = 0
    for rate in allauth_ratelimit.get_rates(
        app="allauth.account", action="confirm_email"
    ):
        cache_key = allauth_ratelimit.get_cache_key(
            request,
            app="allauth.account",
            action="confirm_email",
            rate=rate,
            key=email.lower(),
        )
        # Newest first, as allauth keeps it; a slot frees when the oldest
        # hit still inside the window leaves it.
        history = [ts for ts in cache.get(cache_key, []) if ts > now - rate.duration]
        if len(history) >= rate.amount:
            wait = max(wait, history[rate.amount - 1] + rate.duration - now)
    return math.ceil(wait)


@register.filter
def minutes_seconds(seconds):
    """``seconds`` as a clock, "0:08" or "2:30", the form the code page's
    countdown script also writes, so no plural is needed as it ticks."""
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"
