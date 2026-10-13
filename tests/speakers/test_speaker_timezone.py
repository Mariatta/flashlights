"""A speaker's timezone is optional, and an in-person edition never asks:
times are the event's unless the speaker names their own."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import EventFormat
from speakers.forms import PresenterForm, ProposalProfileForm, SpeakerProfileForm
from speakers.models import SpeakerSettings, edition_clock
from tests.grants import on_team

from .factories import add_presenter, make_presenter, make_session, make_settings

SCHEDULE = reverse("speakers:my_schedule")


@pytest.fixture
def online(conference):
    return make_settings(conference, conference_timezone="America/Los_Angeles")


@pytest.fixture
def in_person(online):
    online.event_format = EventFormat.IN_PERSON
    online.save()
    return online


def speaker(conference, timezone=""):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    presenter = make_presenter(
        conference, user=user, display_name="Ada", timezone=timezone
    )
    add_presenter(make_session(conference), presenter, confirmed=True)
    return presenter


@pytest.mark.django_db
class TestDisplayTimezone:
    def test_blank_follows_the_event(self, conference, online):
        presenter = speaker(conference)
        assert presenter.timezone == ""
        assert presenter.display_timezone == "America/Los_Angeles"
        assert str(presenter.tzinfo) == "America/Los_Angeles"

    def test_their_own_wins_online(self, conference, online):
        assert speaker(conference, "Africa/Lagos").display_timezone == "Africa/Lagos"

    def test_in_person_is_always_the_events(self, conference, in_person):
        presenter = speaker(conference, "Africa/Lagos")
        assert not presenter.asks_timezone
        assert presenter.display_timezone == "America/Los_Angeles"

    def test_no_settings_row_is_utc(self, conference):
        SpeakerSettings.objects.filter(conference=conference).delete()
        assert edition_clock(conference.pk) == (True, "UTC")

    def test_a_batch_reads_the_clock_once(self, conference, in_person):
        presenter = speaker(conference, "Africa/Lagos")
        presenter.use_clock(edition_clock(conference.pk))
        assert presenter.display_timezone == "America/Los_Angeles"


@pytest.mark.django_db
class TestForms:
    def test_optional_online(self, conference, online):
        presenter = speaker(conference)
        for form in (
            SpeakerProfileForm(instance=presenter),
            PresenterForm(instance=presenter, conference=conference),
            ProposalProfileForm(conference=conference),
        ):
            field = form.fields["timezone"]
            assert not field.required
            assert field.choices[0] == ("", "Same as the event")

    def test_not_asked_in_person(self, conference, in_person):
        presenter = speaker(conference)
        for form in (
            SpeakerProfileForm(instance=presenter),
            PresenterForm(instance=presenter, conference=conference),
            ProposalProfileForm(conference=conference),
        ):
            assert "timezone" not in form.fields


@pytest.mark.django_db
class TestPages:
    def page(self, client, presenter):
        client.force_login(presenter.user)
        response = client.get(SCHEDULE)
        assert response.status_code == 200, response.status_code
        return response.content.decode()

    def test_schedule_in_person(self, client, conference, in_person):
        page = self.page(client, speaker(conference, "Africa/Lagos"))
        assert "Times are local to the event, America/Los_Angeles." in page

    def test_schedule_with_their_own(self, client, conference, online):
        page = self.page(client, speaker(conference, "Africa/Lagos"))
        assert "shown in your timezone, Africa/Lagos" in page

    def test_schedule_with_none_named(self, client, conference, online):
        page = self.page(client, speaker(conference))
        assert "s timezone, America/Los_Angeles; to see them in yours" in page

    def test_presenter_page_shows_only_a_named_one(self, client, conference, online):
        organizer = on_team(User.objects.create_user(username="org"))
        client.force_login(organizer)
        presenter = speaker(conference)
        url = reverse("speakers:presenter_detail", args=[presenter.slug])
        assert "· America/Los_Angeles" not in client.get(url).content.decode()
        presenter.timezone = "Africa/Lagos"
        presenter.save()
        assert "· Africa/Lagos" in client.get(url).content.decode()
