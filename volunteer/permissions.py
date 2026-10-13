"""Who may see and run the volunteer side.

Read predicates only (design §7.1). Being a lead of a particular team is a
relation, not a permission, and stays a data check (``leads_team``).
"""

from common.permissions import users_with_perm
from portal.models import Conference

from .constants import BASELINE_APPROVED_VOLUNTEER, ApplicationStatus
from .permission_presets import describe, permissions_for

VIEW_VOLUNTEERS = "volunteer.view_volunteerprofile"
REVIEW_VOLUNTEERS = "volunteer.review_volunteerprofile"
ADD_TEAM = "volunteer.add_team"
CHANGE_TEAM = "volunteer.change_team"
DELETE_TEAM = "volunteer.delete_team"
VOLUNTEER_NOTIFICATIONS = "volunteer.receive_volunteer_notifications"


def can_view_volunteers(user):
    """May open the volunteers list and other people's profiles."""
    return user.has_perm(VIEW_VOLUNTEERS)


def can_review_volunteers(user):
    """May approve, waitlist and otherwise manage applications."""
    return user.has_perm(REVIEW_VOLUNTEERS)


def leads_team(user, team):
    """Whether ``user`` leads ``team``: a relation, never a permission."""
    return team is not None and team.team_leads.filter(user=user).exists()


def volunteer_notification_recipients():
    """Everyone who gets the internal volunteer emails, by any route."""
    return users_with_perm(VOLUNTEER_NOTIFICATIONS)


def permission_sources(profile):
    """What ``profile``'s account may do and where each grant comes from:
    ``[(source, [(group, [words])])]``, in the order the backends apply.

    Team grants belong to the active edition, so a profile from another
    year lists its teams as granting nothing today.
    """
    user = profile.user
    sources = []
    if user.is_superuser:
        sources.append(
            ("Superuser", [("Everything", ["Django's bypass: every permission"])])
        )
    for group in user.groups.all().prefetch_related("permissions"):
        sources.append((f"Group: {group.name}", describe(group.permissions.all())))
    active = Conference.get_active()
    approved = profile.application_status == ApplicationStatus.APPROVED
    if active is None or profile.conference_id != active.pk or not approved:
        return sources
    sources.append(
        (
            f"Approved volunteer, {active.year}",
            describe(permissions_for(BASELINE_APPROVED_VOLUNTEER)),
        )
    )
    for team in profile.teams.filter(conference=active).order_by("short_name"):
        sources.append((f"Team: {team.short_name}", describe(team.permissions.all())))
        if team.team_leads.filter(pk=profile.pk).exists():
            sources.append(
                (f"Lead of {team.short_name}", describe(team.lead_permissions.all()))
            )
    return sources
