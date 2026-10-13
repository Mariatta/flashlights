from enum import StrEnum

# Granted to every approved volunteer of the active edition, tied to no team
# (design §7.1); read by the team permissions backend and the profile page.
BASELINE_APPROVED_VOLUNTEER = frozenset({"sponsorship.view_sponsorshipprofile"})


class RoleTypes(StrEnum):
    """The volunteer roles as they were. Access comes from team permissions
    now and nothing reads roles; the Role model stays because it is
    upstream's, and this enum because ``volunteer/0001_initial`` seeds from
    it and must stay importable."""

    ADMIN = "Admin"
    STAFF = "Staff"
    VENDOR = "Vendor"
    VOLUNTEER = "Volunteer"


class ApplicationStatus(StrEnum):
    """Application status for the volunteer."""

    PENDING = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"
    WAITLISTED = "Waitlisted"


class Region(StrEnum):
    """Region where the volunteer usually reside."""

    NO_REGION = ""
    ASIA = "Asia"
    EUROPE = "Europe"
    NORTH_AMERICA = "North America"
    SOUTH_AMERICA = "South America"
    AFRICA = "Africa"
    OCEANIA = "Oceania"
