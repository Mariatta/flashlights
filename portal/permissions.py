"""Who may run the portal itself: the Organize surface and the editions.

Read predicates only (design §7.1). Teams grant through
``volunteer.auth_backends.TeamPermissionsBackend``; these wrap ``has_perm``
so the codenames live in one place and call sites read well.
"""

ORGANIZE = "portal.view_organizer_dashboard"
MANAGE_CONFERENCES = "portal.change_conference"
START_NEXT_YEAR = "portal.start_next_year"


def is_organizer(user):
    """May open the organizer dashboard and the Organize rail."""
    return user.has_perm(ORGANIZE)


def can_manage_conferences(user):
    """May list, edit and delete editions."""
    return user.has_perm(MANAGE_CONFERENCES)


def can_start_next_year(user):
    """May stand up the next edition."""
    return user.has_perm(START_NEXT_YEAR)
