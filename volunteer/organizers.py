"""Who changes what a team may do. Kept apart from ``permissions``, which
the models import, since this reads the teams themselves."""

from django.db.models import Q

from portal.models import Conference

from .constants import ApplicationStatus
from .models import Team
from .permission_presets import ORGANIZERS, PRESETS, permissions_for


def is_on_organizers_team(user):
    """An approved member or a lead of the active edition's Organizers team,
    or a superuser. Only they change what a team may do: a team editor who
    could tick permissions would grant them to their own team."""
    if user.is_superuser:
        return True
    active = Conference.get_active()
    if active is None:
        return False
    return (
        Team.objects.filter(conference=active, short_name=ORGANIZERS)
        .filter(
            Q(
                members__user=user,
                members__application_status=ApplicationStatus.APPROVED,
            )
            | Q(team_leads__user=user)
        )
        .exists()
    )


def ensure_organizers_team(conference):
    """The edition's Organizers team, made from its preset when the edition
    has none: an edition that switches the speaker module on can then be
    run by people who are not superusers. Returns the team."""
    team, created = Team.objects.get_or_create(
        conference=conference,
        short_name=ORGANIZERS,
        defaults={"open_to_new_members": False},
    )
    if created:
        preset = PRESETS[ORGANIZERS]
        team.permissions.set(permissions_for(preset.members))
        team.lead_permissions.set(permissions_for(preset.leads))
    return team
