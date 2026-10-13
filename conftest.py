import unittest
from datetime import date, timedelta

import pytest
from captcha.models import CaptchaStore

from portal.models import Conference
from tests.ticketing_ids import ANONYMOUS_QUESTION, NOT_ANONYMOUS
from volunteer.constants import ApplicationStatus
from volunteer.models import Language, Team, VolunteerProfile
from volunteer.permission_presets import ORGANIZERS, PRESETS, permissions_for


@pytest.fixture(autouse=True)
def agreed_accounts(request, monkeypatch):
    """Treat every account in the suite as having agreed to the Code of
    Conduct and Terms of Service.

    ``portal_account.agreements.AgreementRequiredMiddleware`` redirects a
    signed-in account that has not, which is the whole point of the gate and
    would otherwise turn nearly every page test into a 302 about something
    the test is not asking about. Patching the predicate leaves the database
    alone, so tests that manage profiles themselves are unaffected. A test of
    the gate carries the ``no_agreements`` marker and gets the real one.
    """
    if "no_agreements" not in request.keywords:
        monkeypatch.setattr("portal_account.agreements.has_agreed", lambda user: True)


@pytest.fixture
def portal_user(db, django_user_model):
    username = "testuser"
    password = "testpassword"
    email = "test@example.com"
    first_name = "fname"
    last_name = "lname"
    return django_user_model.objects.create_user(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


@pytest.fixture
def admin_user(db, django_user_model):
    username = "adminuser"
    password = "adminpassword"
    email = "admin@example.com"
    first_name = "admin_fname"
    last_name = "admin_lname"
    return django_user_model.objects.create_superuser(
        username=username,
        password=password,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


@pytest.fixture
def language(db):
    return Language.objects.create(code="en", name="English")


@pytest.fixture(autouse=True)
def conference(request):
    """The active conference every year-bound record is scoped to.

    Autouse so production paths calling ``Conference.get_active()`` resolve in
    every test, and so inline model construction can request it by name. Tests
    that manage their own Conference rows override this fixture locally (see
    ``tests/portal/test_models.py``).

    ``unittest.TestCase`` classes manage their own transactions, so this
    db-backed row would leak across them and clash on the unique year; those
    classes are skipped here and seed their own Conference in ``setUp``.
    """
    if request.cls is not None and issubclass(request.cls, unittest.TestCase):
        return None
    request.getfixturevalue("db")
    return Conference.objects.create(
        year=2025,
        name="Flashlights 2025",
        slug="2025",
        is_active=True,
        # The landing advertises volunteering only while this is on.
        volunteer_application_open=True,
        pretix_event_slug="2025",
        sponsorship_goal=15000,
        donation_goal=2500,
        # In the past, so the active edition is "over" by default and the
        # start-a-new-year flow is available. Gate-specific tests override this.
        conference_date=date.today() - timedelta(days=30),
    )


@pytest.fixture
def pretix_order_data():
    return {
        "code": "ORDER123",
        "event": "2025",
        "status": "p",
        "testmode": False,
        "email": "attendee@example.com",
        "datetime": "2025-11-13T17:12:03.989259+01:00",
        "total": "30.00",
        "positions": [
            {
                "attendee_name": "Example Attendee",
                "answers": [
                    {"question_identifier": "QUESTION123", "option_identifiers": []},
                    {
                        "option_identifiers": [NOT_ANONYMOUS],
                        "question_identifier": ANONYMOUS_QUESTION,
                    },
                ],
            }
        ],
        "last_modified": "2025-11-13T17:12:07.002602+01:00",
        "url": "https://someurl/",
        "cancellation_date": None,
    }


@pytest.fixture
def captcha_solution(db):
    """POST data that solves a freshly generated CAPTCHA challenge.

    Any test that submits the signup form needs to merge this in; the field
    rejects a missing or wrong answer.
    """
    key = CaptchaStore.generate_key()
    answer = CaptchaStore.objects.get(hashkey=key).response
    return {"captcha_0": key, "captcha_1": answer}


@pytest.fixture
def preset_team(conference):
    """A team of the active edition carrying one of the §7.1 presets, made
    on first use and reused after: ``preset_team("Sponsorship")``."""

    def _team(name):
        team, created = Team.objects.get_or_create(
            conference=conference, short_name=name, defaults={"description": name}
        )
        if created:
            team.permissions.set(permissions_for(PRESETS[name].members))
            team.lead_permissions.set(permissions_for(PRESETS[name].leads))
        return team

    return _team


@pytest.fixture
def join_team(preset_team):
    """Put an account on a preset team: an approved profile in the active
    edition, and membership (leadership too when asked). Returns the account.
    An existing profile is reused as it is: a test that made one pending and
    then expects access is asking for two things at once."""

    def _join(user, name, lead=False):
        team = preset_team(name)
        profile, _ = VolunteerProfile.objects.get_or_create(
            user=user,
            conference=team.conference,
            defaults={"application_status": ApplicationStatus.APPROVED},
        )
        profile.teams.add(team)
        if lead:
            team.team_leads.add(profile)
        return user

    return _join


@pytest.fixture
def grant_organizer(join_team):
    """Put an account on the Organizers team. Returns the account."""

    def _grant(user, lead=False):
        return join_team(user, ORGANIZERS, lead=lead)

    return _grant


@pytest.fixture
def organizer(django_user_model, grant_organizer):
    """A non-staff, non-superuser account whose access comes from the
    Organizers team alone: the shape every organizer has after Stage 3."""
    return grant_organizer(
        django_user_model.objects.create_user(
            username="organizer", email="organizer@example.com", first_name="Org"
        )
    )
