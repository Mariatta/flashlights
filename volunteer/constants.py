from enum import StrEnum


class RoleTypes(StrEnum):
    """Role types for the volunteer."""

    ADMIN = "Admin"
    STAFF = "Staff"
    VENDOR = "Vendor"
    VOLUNTEER = "Volunteer"


# Granted to every approved volunteer of the active edition, tied to no team
# (design §7.1); read by the team permissions backend and the profile page.
BASELINE_APPROVED_VOLUNTEER = frozenset({"sponsorship.view_sponsorshipprofile"})


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
