"""Who may see and run sponsorship.

Read predicates only (design §7.1). Reading sponsors is every approved
volunteer's, as the team backend's baseline grant; managing them is the
Sponsorship set. Which editions a reader may open stays a data check on
the views (``CanViewSponsorship.viewable_conferences``).
"""

from common.permissions import users_with_perm

VIEW_SPONSORS = "sponsorship.view_sponsorshipprofile"
ADD_SPONSOR = "sponsorship.add_sponsorshipprofile"
CHANGE_SPONSOR = "sponsorship.change_sponsorshipprofile"
DELETE_SPONSOR = "sponsorship.delete_sponsorshipprofile"
SEND_INVOICE = "sponsorship.send_invoice"
VIEW_UNCONFIRMED = "sponsorship.view_unconfirmed_sponsors"
ADD_TIER = "sponsorship.add_sponsorshiptier"
CHANGE_TIER = "sponsorship.change_sponsorshiptier"
DELETE_TIER = "sponsorship.delete_sponsorshiptier"
SPONSORSHIP_NOTIFICATIONS = "sponsorship.receive_sponsorship_notifications"


def can_view_sponsors(user):
    return user.has_perm(VIEW_SPONSORS)


def can_manage_sponsors(user):
    """Edits sponsors: the manager's view of the list, every edition."""
    return user.has_perm(CHANGE_SPONSOR)


def can_send_invoice(user):
    return user.has_perm(SEND_INVOICE)


def can_view_unconfirmed(user):
    """Sees sponsors whose status is not yet a commitment."""
    return user.has_perm(VIEW_UNCONFIRMED)


def sponsor_contact_candidates():
    """Who may be a sponsor's internal contact: anyone who manages sponsors."""
    return users_with_perm(CHANGE_SPONSOR)


def sponsorship_notification_recipients():
    """Everyone who gets the internal sponsorship emails, by any route."""
    return users_with_perm(SPONSORSHIP_NOTIFICATIONS)
