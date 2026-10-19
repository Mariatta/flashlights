"""Who changes what a team may do, and the Organizers team itself. Kept
apart from ``permissions``, which the models import, since this writes
teams."""

from portal.permissions import is_organizer

from .models import Team
from .permission_presets import ORGANIZERS, PRESETS, permissions_for


def may_change_grants(user):
    """Whether ``user`` may change what a team may do: whoever holds the
    Organize dashboard, which only the Organizers preset carries (and
    superusers). Read as a permission, never from a team's name, which any
    team editor can set."""
    return is_organizer(user)


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
