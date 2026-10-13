from django import template
from django.utils.safestring import mark_safe

from portal.models import Conference
from speakers.constants import SessionStatus
from speakers.editions import program_editions, working_edition
from speakers.markdown import render_md
from speakers.people import user_label
from speakers.permissions import can_work_sessions
from speakers.tables import INVITATION_BADGE_CLASSES, STATUS_BADGE_CLASSES

register = template.Library()


@register.filter
def speaker_md(value):
    """Render a speaker-facing markdown field to sanitized HTML."""
    return mark_safe(render_md(value))


@register.filter
def session_status_class(session):
    """Bootstrap badge class for a session's status chip."""
    return STATUS_BADGE_CLASSES[SessionStatus(session.status)]


@register.filter
def invitation_status_class(invitation):
    """Bootstrap badge class for an invitation's status chip."""
    return INVITATION_BADGE_CLASSES[invitation.status]


@register.filter
def duration(seconds):
    """Whole seconds as "1 min 30 s", "45 s", or "1 h 02 min 03 s".

    A video's length is shown to the second, since the limit is checked
    to the second: "1 min" for a 1:59 clip would hide the minute that
    matters.
    """
    if seconds is None:
        return ""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min {secs:02d} s"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


register.filter("user_label", user_label)


@register.inclusion_tag("speakers/_edition_switcher.html", takes_context=True)
def edition_switcher(context):
    """Which edition the program pages show, and the others an organizer may
    plan: the active one and any newer one with the speaker portal on."""
    request = context["request"]
    user = request.user
    editions = [one for one in program_editions() if can_work_sessions(user, one)]
    return {
        "editions": editions if len(editions) > 1 else [],
        "working": working_edition(request),
        "active": Conference.get_active(),
        "next": request.get_full_path(),
        "csrf_token": context.get("csrf_token"),
    }
