"""The Discord username on a presenter: one of the person's handles, kept
on the account and shared with the volunteer side."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal.models import Conference
from portal.validators import validate_discord_username
from portal_account.handles import handles_of
from speakers.models import Presenter
from speakers.program_types import session_type
from speakers.seeds import seed_checklists
from speakers.services import link_presenter_user
from tests.grants import on_team
from volunteer.forms import VolunteerProfileForm
from volunteer.models import VolunteerProfile

from .factories import add_presenter, make_presenter, make_session, make_settings

PROFILE = reverse("speakers:my_profile")
PROPOSE = reverse("speakers:propose")
FIELD = 'name="discord_username"'


@pytest.fixture
def enabled(conference):
    seed_checklists(conference)
    return make_settings(conference, proposals_open=True)


@pytest.fixture
def speaker(db):
    return User.objects.create_user(username="ada", email="ada@example.com")


@pytest.fixture
def presenter(conference, enabled, speaker):
    """On the program, so the speaker area opens."""
    presenter = make_presenter(
        conference, display_name="Ada", email="ada@example.com", user=speaker
    )
    add_presenter(make_session(conference), presenter, confirmed=True)
    return presenter


@pytest.fixture
def organizer(db):
    return on_team(
        User.objects.create_user(username="organizer", email="org@example.com")
    )


def volunteer(user, conference, username):
    return VolunteerProfile.objects.create(
        user=user, conference=conference, discord_username=username
    )


@pytest.mark.parametrize(
    "value, message",
    [
        ("ada_l.1", None),
        ("a", "between 2 and 32"),
        ("a" * 33, "between 2 and 32"),
        ("ada..l", "two consecutive periods"),
        ("ada#1234", "alphanumeric"),
    ],
)
def test_the_validator_is_the_volunteer_forms_rule(value, message):
    if message is None:
        validate_discord_username(value)
        return
    with pytest.raises(ValidationError, match=message):
        validate_discord_username(value)


@pytest.mark.django_db
class TestSpeakerProfile:
    def test_asked_on_the_profile_form(self, client, speaker, presenter):
        client.force_login(speaker)
        assert FIELD in client.get(PROFILE).content.decode()
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "ada..l"},
        )
        assert "two consecutive periods" in response.content.decode()
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "ada_l"},
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_l"
        assert handles_of(speaker) == {"discord": "ada_l"}

    def test_the_volunteers_value_is_there_and_a_change_follows_everywhere(
        self, client, conference, speaker, presenter
    ):
        profile = volunteer(speaker, conference, "ada_vol")
        client.force_login(speaker)
        page = client.get(PROFILE).content.decode()
        assert FIELD in page and 'value="ada_vol"' in page
        response = client.post(
            PROFILE,
            {"display_name": "Ada", "timezone": "UTC", "discord_username": "ada_new"},
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        profile.refresh_from_db()
        assert presenter.discord_username == profile.discord_username == "ada_new"

    def test_the_organizer_form_edits_the_persons_handle(
        self, client, conference, organizer, speaker, presenter
    ):
        profile = volunteer(speaker, conference, "ada_vol")
        client.force_login(organizer)
        url = reverse("speakers:presenter_edit", args=[presenter.slug])
        assert 'value="ada_vol"' in client.get(url).content.decode()
        response = client.post(
            url,
            {
                "display_name": "Ada",
                "email": "ada@example.com",
                "timezone": "UTC",
                "discord_username": "org_set",
            },
        )
        assert response.status_code == 302
        presenter.refresh_from_db()
        profile.refresh_from_db()
        assert presenter.discord_username == profile.discord_username == "org_set"

    def test_pronouns_come_from_the_account_and_go_back_to_it(
        self, client, speaker, presenter
    ):
        account = speaker.portalprofile
        account.pronouns = "she/her"
        account.save()
        client.force_login(speaker)
        assert 'value="she/her"' in client.get(PROFILE).content.decode()
        response = client.post(
            PROFILE, {"display_name": "Ada", "timezone": "UTC", "pronouns": "they"}
        )
        assertRedirects(response, PROFILE)
        account.refresh_from_db()
        presenter.refresh_from_db()
        assert account.pronouns == presenter.pronouns == "they"

    def test_a_mastodon_handle_is_stored_as_its_url(
        self, client, conference, speaker, presenter
    ):
        """The model's URL field would refuse ``@ada@fosstodon.org``; the
        handle fields are plain text so the catalogue gets to normalise."""
        client.force_login(speaker)
        response = client.post(
            PROFILE,
            {
                "display_name": "Ada",
                "timezone": "UTC",
                "mastodon_url": "@ada@fosstodon.org",
                "website_url": "ada.example.org",
                "linkedin_url": "not-linkedin.example.org/ada",
            },
        )
        assert "LinkedIn" in response.content.decode()
        response = client.post(
            PROFILE,
            {
                "display_name": "Ada",
                "timezone": "UTC",
                "mastodon_url": "@ada@fosstodon.org",
                "website_url": "ada.example.org",
            },
        )
        assertRedirects(response, PROFILE)
        presenter.refresh_from_db()
        assert presenter.mastodon_url == "https://fosstodon.org/@ada"
        assert presenter.website_url == "https://ada.example.org"

    def test_the_organizer_form_for_a_row_with_no_account_writes_the_row(
        self, client, conference, organizer, enabled
    ):
        invited = make_presenter(conference, email="sam@example.com")
        client.force_login(organizer)
        url = reverse("speakers:presenter_edit", args=[invited.slug])
        response = client.post(
            url,
            {
                "display_name": "Sam",
                "email": "sam@example.com",
                "timezone": "UTC",
                "discord_username": "sam_own",
            },
        )
        assert response.status_code == 302
        invited.refresh_from_db()
        assert invited.discord_username == "sam_own"

    def test_the_organizer_page_lists_every_handle(self, client, organizer, presenter):
        """Blank ones show as blank, so an organizer can see what is missing."""
        client.force_login(organizer)
        url = reverse("speakers:presenter_detail", args=[presenter.slug])
        page = client.get(url).content.decode()
        for label in (
            "Website",
            "GitHub",
            "Mastodon",
            "LinkedIn",
            "Bluesky",
            "Discord",
        ):
            assert f"<strong>{label}:</strong>" in page
        presenter.discord_username = "ada_l"
        presenter.github_username = "ada"
        presenter.bluesky_username = "ada.bsky.social"
        presenter.save()
        page = client.get(url).content.decode()
        assert "ada_l" in page
        assert 'href="https://github.com/ada"' in page
        assert 'href="https://bsky.app/profile/ada.bsky.social"' in page


@pytest.mark.django_db
class TestFollowsThePerson:
    def test_saving_the_volunteer_form_updates_the_presenter_rows(
        self, conference, speaker, presenter, language
    ):
        other = make_presenter(
            conference,
            user=User.objects.create_user("grace", email="grace@example.com"),
            discord_username="grace_h",
        )
        presenter.discord_username = "old"
        presenter.save()
        data = {
            "language": [language.id],
            "github_username": "ada",
            "discord_username": "ada_vol",
            "availability_hours_per_week": 2,
        }
        form = VolunteerProfileForm(user=speaker, data=data)
        assert form.is_valid(), form.errors
        profile = form.save()
        presenter.refresh_from_db()
        assert presenter.discord_username == "ada_vol"
        assert presenter.github_username == "ada"
        form = VolunteerProfileForm(
            user=speaker, instance=profile, data={**data, "discord_username": "newer"}
        )
        assert form.is_valid(), form.errors
        form.save()
        presenter.refresh_from_db()
        assert presenter.discord_username == "newer"
        other.refresh_from_db()
        assert other.discord_username == "grace_h"

    def test_the_newest_volunteer_profile_speaks_for_a_person_with_no_record(
        self, conference, speaker, presenter
    ):
        past = Conference.objects.create(
            year=2024, name="Flashlights 2024", slug="2024"
        )
        volunteer(speaker, past, "ada_2024")
        volunteer(speaker, conference, "ada_now")
        assert handles_of(speaker)["discord"] == "ada_now"
        assert handles_of(None) == {}

    def test_accepting_an_invitation_takes_the_volunteers_username(
        self, conference, enabled
    ):
        user = User.objects.create_user("sam", email="sam@example.com")
        EmailAddress.objects.create(
            user=user, email="sam@example.com", verified=True, primary=True
        )
        volunteer(user, conference, "sam_vol")
        invited = make_presenter(conference, email="sam@example.com")
        assert link_presenter_user(invited) == user
        invited.refresh_from_db()
        assert invited.discord_username == "sam_vol"
        assert handles_of(user) == {"discord": "sam_vol"}

    def test_the_person_wins_over_what_an_organizer_typed(self, conference, enabled):
        """The volunteer profile is the person's own word; a handle the
        organizer typed on the row fills only what the person left blank."""
        user = User.objects.create_user("sam", email="sam@example.com")
        EmailAddress.objects.create(
            user=user, email="sam@example.com", verified=True, primary=True
        )
        volunteer(user, conference, "sam_vol")
        invited = make_presenter(
            conference,
            email="sam@example.com",
            discord_username="sam_own",
            github_username="sam-gh",
        )
        link_presenter_user(invited)
        invited.refresh_from_db()
        assert invited.discord_username == "sam_vol"
        assert invited.github_username == "sam-gh"
        assert handles_of(user) == {"discord": "sam_vol", "github": "sam-gh"}


def propose(client, conference, **extra):
    data = {
        "you-display_name": "Sam Newcomer",
        "you-bio_md": "I write tests.",
        "you-timezone": "UTC",
        "session-kind": session_type(conference, "TALK").pk,
        "session-title": "A talk about testing",
        "session-summary_md": "What testing is for.",
        "session-level": "ALL",
        "session-language": "en",
    }
    data.update(extra)
    return client.post(PROPOSE, data, follow=True)


@pytest.mark.django_db
class TestProposing:
    @pytest.fixture
    def stranger(self, db):
        return User.objects.create_user(username="sam", email="sam@example.com")

    def test_a_stranger_is_asked(self, client, conference, enabled, stranger):
        assert client.get(PROPOSE).status_code == 200  # signed out: no user
        client.force_login(stranger)
        assert 'name="you-discord_username"' in client.get(PROPOSE).content.decode()
        propose(client, conference, **{"you-discord_username": "sam_d"})
        assert Presenter.objects.get(user=stranger).discord_username == "sam_d"
        assert handles_of(stranger) == {"discord": "sam_d"}

    def test_a_volunteer_finds_theirs_filled_in(
        self, client, conference, enabled, stranger
    ):
        profile = volunteer(stranger, conference, "sam_vol")
        client.force_login(stranger)
        page = client.get(PROPOSE).content.decode()
        assert 'name="you-discord_username"' in page and 'value="sam_vol"' in page
        propose(client, conference, **{"you-discord_username": "other"})
        assert Presenter.objects.get(user=stranger).discord_username == "other"
        profile.refresh_from_db()
        assert profile.discord_username == "other"


@pytest.mark.django_db
class TestVolunteerForm:
    def test_prefills_from_the_presenter_row(self, conference, speaker, presenter):
        presenter.discord_username = "ada_spk"
        presenter.save()
        assert (
            VolunteerProfileForm(user=speaker).initial["discord_username"] == "ada_spk"
        )

    def test_a_prior_volunteer_profile_wins(self, conference, speaker, presenter):
        presenter.discord_username = "ada_spk"
        presenter.save()
        past = Conference.objects.create(
            year=2024, name="Flashlights 2024", slug="2024"
        )
        volunteer(speaker, past, "ada_2024")
        assert (
            VolunteerProfileForm(user=speaker).initial["discord_username"] == "ada_2024"
        )

    def test_nothing_to_prefill(self, speaker, presenter):
        assert "discord_username" not in VolunteerProfileForm(user=speaker).initial
