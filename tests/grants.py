"""Granting access in tests the way the portal does: through a team of the
active edition carrying one of the presets. The conftest fixtures
(``preset_team``, ``join_team``, ``grant_organizer``) wrap the same steps;
this plain function serves module-level fixtures and inline accounts."""

from django.core import mail

from common.models import SentEmail
from portal.models import Conference
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile
from volunteer.permission_presets import ORGANIZERS, PRESETS, permissions_for


def on_team(user, name=ORGANIZERS, lead=False):
    """Put ``user`` on the active edition's preset team ``name``, approved.
    Returns the user, so it wraps ``create_user``. The volunteer emails that
    creating the profile sends are taken back out of the outbox and the
    sent-email record: the test is
    about what comes after, not about this setup."""
    outbox = getattr(mail, "outbox", None)
    sent = len(outbox) if outbox is not None else 0
    last_record = SentEmail.objects.order_by("-pk").values_list("pk", flat=True).first()
    conference = Conference.get_active()
    team, created = Team.objects.get_or_create(
        conference=conference, short_name=name, defaults={"description": name}
    )
    if created:
        team.permissions.set(permissions_for(PRESETS[name].members))
        team.lead_permissions.set(permissions_for(PRESETS[name].leads))
    profile, _ = VolunteerProfile.objects.get_or_create(
        user=user,
        conference=conference,
        defaults={"application_status": ApplicationStatus.APPROVED},
    )
    profile.teams.add(team)
    if lead:
        team.team_leads.add(profile)
    if outbox is not None:
        del outbox[sent:]
    SentEmail.objects.filter(pk__gt=last_record or 0).delete()
    return user
