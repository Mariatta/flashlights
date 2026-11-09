"""Affiliations beyond the volunteer profile: the account page, the
speaker profile, the proposal form, and where organizers and the public
read them."""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from affiliations.models import Affiliation, AffiliationKind
from portal_account.models import PortalProfile
from speakers.api import presenter_payload
from speakers.models import Proposal
from speakers.program_types import session_type
from speakers.seeds import seed_checklists
from tests.speakers.factories import (
    add_presenter,
    make_presenter,
    make_session,
    make_settings,
)

from .test_affiliations import rows

PROPOSE = reverse("speakers:propose")
MY_PROFILE = reverse("speakers:my_profile")


@pytest.fixture
def enabled(conference):
    settings_row = make_settings(conference, proposals_open=True)
    seed_checklists(conference)
    return settings_row


@pytest.fixture
def ada(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.mark.django_db
class TestTheAccountPage:
    def test_the_profile_form_edits_the_rows(self, client, ada):
        account = PortalProfile.objects.create(
            user=ada, coc_agreement=True, tos_agreement=True
        )
        client.force_login(ada)
        url = reverse("portal_account:portal_profile_edit", args=[account.pk])
        page = client.get(url).content.decode()
        assert "affiliations-TOTAL_FORMS" in page and "affiliations/formset." in page
        response = client.post(
            url,
            {
                "first_name": "Ada",
                "last_name": "L",
                "pronouns": "",
                **rows((AffiliationKind.PROJECT, "CPython", "")),
            },
        )
        assert response.status_code == 302
        assert [str(a) for a in ada.affiliations.all()] == ["Project: CPython"]

    def test_the_create_page_takes_rows_too(self, client, ada):
        client.force_login(ada)
        url = reverse("portal_account:portal_profile_new")
        assert "affiliations-TOTAL_FORMS" in client.get(url).content.decode()
        response = client.post(
            url,
            {
                "first_name": "Ada",
                "last_name": "L",
                "pronouns": "",
                **rows((AffiliationKind.WORKPLACE, "Acme", "https://acme.example")),
            },
        )
        assert response.status_code == 302
        assert ada.affiliations.get().url == "https://acme.example"


@pytest.mark.django_db
class TestTheSpeakerSide:
    def test_the_proposal_form_saves_rows_and_the_queue_shows_them(
        self, client, conference, enabled, ada, grant_organizer
    ):
        client.force_login(ada)
        page = client.get(PROPOSE).content.decode()
        assert "affiliations-TOTAL_FORMS" in page
        # The rows are rendered field by field, so the widgets carry the
        # Bootstrap classes themselves.
        first_row = page.index("data-affiliation-row")
        card_end = page.index("data-affiliation-add")
        row = page[first_row:card_end]
        for name, css in (
            ("kind", "form-select"),
            ("name", "form-control"),
            ("url", "form-control"),
            ("DELETE", "form-check-input"),
        ):
            assert f'name="affiliations-0-{name}" class="{css}"' in row, name
        data = {
            "you-display_name": "Ada",
            "you-bio_md": "Hi.",
            "you-timezone": "UTC",
            "session-kind": session_type(conference, "TALK").pk,
            "session-title": "Counting",
            "session-summary_md": "Numbers.",
            "session-language": "en",
            **rows((AffiliationKind.PROJECT, "Analytical Engine", "")),
        }
        # A bad row keeps the whole page, counted under "About you".
        response = client.post(PROPOSE, {**data, "affiliations-0-url": "not a url"})
        assert response.status_code == 200
        assert '1 in "About you"' in response.content.decode()
        assert not Proposal.objects.exists()
        assert client.post(PROPOSE, data).status_code == 302
        assert [a.name for a in ada.affiliations.all()] == ["Analytical Engine"]
        organizer = grant_organizer(
            User.objects.create_user(username="org", email="org@example.com")
        )
        client.force_login(organizer)
        content = client.get(reverse("speakers:proposal_queue")).content.decode()
        assert "proposed by Ada" in content and "(Analytical Engine)" in content
        presenter = Proposal.objects.get().presenter
        url = reverse("speakers:presenter_detail", args=[presenter.slug])
        content = client.get(url).content.decode()
        assert "Affiliations" in content and "Analytical Engine" in content

    def test_a_post_without_the_rows_leaves_them_alone(
        self, client, conference, enabled, ada
    ):
        Affiliation.objects.create(user=ada, name="Kept")
        client.force_login(ada)
        response = client.post(
            PROPOSE,
            {
                "you-display_name": "Ada",
                "you-bio_md": "Hi.",
                "you-timezone": "UTC",
                "session-kind": session_type(conference, "TALK").pk,
                "session-title": "Counting",
                "session-summary_md": "Numbers.",
                "session-language": "en",
            },
        )
        assert response.status_code == 302
        assert ada.affiliations.get().name == "Kept"

    def test_the_speaker_profile_edits_the_rows(self, client, conference, enabled, ada):
        presenter = make_presenter(conference, display_name="Ada", user=ada)
        add_presenter(make_session(conference), presenter, confirmed=True)
        kept = Affiliation.objects.create(user=ada, name="Old job")
        client.force_login(ada)
        assert "affiliations-TOTAL_FORMS" in client.get(MY_PROFILE).content.decode()
        response = client.post(
            MY_PROFILE,
            {
                "display_name": "Ada",
                "timezone": "UTC",
                **rows(
                    (AffiliationKind.COMMUNITY, "Meetup", ""), existing=[(kept, True)]
                ),
            },
        )
        assert response.status_code == 302
        assert [a.name for a in ada.affiliations.all()] == ["Meetup"]
        response = client.post(
            MY_PROFILE,
            {"display_name": "Ada", "timezone": "UTC", **rows(("bogus", "X", ""))},
        )
        assert response.status_code == 200
        assert [a.name for a in ada.affiliations.all()] == ["Meetup"]

    def test_the_speaker_profile_uses_the_full_width(
        self, client, conference, enabled, ada
    ):
        """The form fills the content column, and each row's Remove
        checkbox sits in a column sized to fit it, so it stays inside
        the card."""
        presenter = make_presenter(conference, display_name="Ada", user=ada)
        add_presenter(make_session(conference), presenter, confirmed=True)
        Affiliation.objects.create(user=ada, name="Old job")
        client.force_login(ada)
        page = client.get(MY_PROFILE).content.decode()
        assert 'class="col-lg-8"' not in page
        assert re.search(r'<div class="col-md-auto">\s*<div class="form-check', page)

    def test_the_public_api_keeps_them_private(self, conference, ada):
        """Organizers see them; the public program does not, until the
        rows carry a notice saying otherwise."""
        presenter = make_presenter(conference, display_name="Ada", user=ada)
        Affiliation.objects.create(
            user=ada, kind=AffiliationKind.PROJECT, name="CPython", url=""
        )
        payload = presenter_payload(presenter, [], "https://x")
        assert "affiliations" not in payload and "CPython" not in str(payload)
