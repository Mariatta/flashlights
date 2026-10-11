"""People in lists (PersonRow spec): an initials avatar, the name, a muted
line of role and team, and a status chip whose tone always comes with a
word. Tables render their cells through these so every list reads alike.
"""

from django.utils.html import format_html

#: tone -> chip class; the colours live in portal.css.
TONES = ("neutral", "ok", "warn", "stop")


def initials(name):
    """Up to two initials, or a question mark for a blank name."""
    parts = [part for part in (name or "").split() if part]
    return "".join(part[0] for part in parts[:2]).upper() or "?"


def person_cell(name, href=None, meta=None):
    """Avatar, name (linked when ``href`` is given) and the meta line."""
    avatar = format_html(
        '<span class="person-avatar" aria-hidden="true">{}</span>', initials(name)
    )
    shown = format_html('<a href="{}">{}</a>', href, name) if href else name
    meta_html = format_html('<div class="person-meta">{}</div>', meta) if meta else ""
    return format_html(
        '<span class="person-cell">{}<span class="min-w-0">'
        '<div class="person-name">{}</div>{}</span></span>',
        avatar,
        shown,
        meta_html,
    )


def status_chip(label, tone="neutral"):
    """A status word in its tone: ok, warn, stop or neutral."""
    if tone not in TONES:
        raise ValueError(f"unknown status tone {tone!r}")
    return format_html(
        '<span class="status-chip status-chip-{}">{}</span>', tone, label
    )
