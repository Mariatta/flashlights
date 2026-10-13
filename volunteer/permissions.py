"""Who may see and run the volunteer side.

Read predicates only (design §7.1). Being a lead of a particular team is a
relation, not a permission, and stays a data check (``leads_team``).
"""

from common.permissions import users_with_perm

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
