import bleach
import markdown as markdown_lib
from django import template
from django.conf import settings
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
