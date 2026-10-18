"""Which edition the program pages work on.

The active edition is what the public sees and whose teams grant access.
Organizers may plan a newer one meanwhile: they choose it as their
working edition, kept in their login session, and every organizer page of
the speaker module follows it. Speakers are taken to the edition they are
on the program of.
"""

from django.db.models import Q

from portal.models import Conference

from .models import Presenter, speaker_module_enabled

SESSION_KEY = "speakers_working_edition"


def program_editions():
    """The editions a program can be worked on: the active one and every
    newer one, each with the speaker portal on, oldest first."""
    active = Conference.get_active()
    if active is None:
        return []
    return list(
        Conference.objects.filter(
            Q(pk=active.pk) | Q(year__gt=active.year),
            speaker_settings__speaker_module_enabled=True,
        ).order_by("year")
    )


def working_edition(request):
    """The edition this person chose to plan, while it is still offered;
    otherwise the active one. When the active edition runs no program,
    the earliest newer one that does, so its organizers can reach it."""
    active = Conference.get_active()
    if active is None:
        return None
    newer = Conference.objects.filter(
        year__gt=active.year, speaker_settings__speaker_module_enabled=True
    )
    # A request built outside the middleware has no session: the active one.
    chosen = getattr(request, "session", {}).get(SESSION_KEY)
    if chosen not in (None, active.pk):
        planned = newer.filter(pk=chosen).first()
        if planned is not None:
            return planned
    if speaker_module_enabled(active):
        return active
    return newer.order_by("year").first() or active


def set_working_edition(request, conference):
    request.session[SESSION_KEY] = conference.pk


def speaker_edition(user, preferred=None):
    """The edition ``user`` is on the program of, among the active and newer
    ones with the speaker portal on: ``preferred`` when it is one of them,
    else the active one, else the earliest. None when they are on none.
    On the program, not merely known: someone whose proposal nobody has
    answered has a presenter row and no speaker pages."""
    if not user.is_authenticated:
        return None
    editions = program_editions()
    on = set(
        Presenter.objects.filter(
            user=user,
            conference__in=editions,
            conference__speaker_settings__speaker_module_enabled=True,
        )
        .onboarded()
        .values_list("conference", flat=True)
    )
    # The active edition is the oldest of them, so first after preferred.
    ordered = ([preferred] if preferred is not None else []) + editions
    return next((edition for edition in ordered if edition.pk in on), None)
