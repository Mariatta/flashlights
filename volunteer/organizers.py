"""Who changes what a team may do. Kept apart from ``permissions``, which
the models import, since this reads the teams themselves."""

from django.db.models import Q

from portal.models import Conference

from .constants import ApplicationStatus
from .models import Team
from .permission_presets import ORGANIZERS


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
