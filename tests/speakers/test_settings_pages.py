"""Organizers open session proposals and list the websites that may
show the program in the portal, not the Django admin."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import EventFormat, Recordings
from speakers.models import ActivityLog, AllowedOrigin, SpeakerSettings
from speakers.schedule import off_grid_warning
from tests.grants import on_team

from .factories import make_session, make_settings, make_slot

SETTINGS = reverse("speakers:speaker_settings")
ORIGINS = reverse("speakers:allowed_origins")
SHARE = reverse("speakers:program_share")


def lead_of_program():
    return on_team(
        User.objects.create_user(username="pam", email="pam@x.org"),
        "Program",
        lead=True,
    )


@pytest.mark.django_db
class TestSpeakerSettingsPage:
    def test_a_program_lead_opens_the_call(self, client, conference):
        make_settings(conference)
        client.force_login(lead_of_program())
        page = client.get(SETTINGS)
        assert page.status_code == 200
        assert "Taking proposals" in page.content.decode()
        response = client.post(
            SETTINGS,
            {
                "proposals_open": "on",
                "proposals_intro_md": "Tell us about your project.",
                "organizers_email": "",
                "conference_timezone": "America/Los_Angeles",
                "schedule_step_minutes": "5",
                "default_premiere_location": "YOUTUBE",
                "default_video_length_limit_minutes": "20",
                "media_for_speakers": "on",
            },
        )
        assert response.status_code == 302
        row = SpeakerSettings.objects.get(conference=conference)
        assert row.proposals_open and row.conference_timezone == "America/Los_Angeles"
        assert row.schedule_step_minutes == 5
        assert ActivityLog.objects.filter(action="speakers.settings_changed").exists()

    def test_the_grid_step_divides_an_hour(self, client, conference):
        row = make_settings(conference)
        assert row.schedule_step_minutes == 15
        client.force_login(lead_of_program())
        page = client.get(SETTINGS)
        field = page.context["form"].fields["schedule_step_minutes"]
        assert [value for value, _ in field.choices] == [
            1,
            2,
            3,
            4,
            5,
            6,
            10,
            12,
            15,
            20,
            30,
            60,
        ]
        assert "Schedule grid step" in page.content.decode()
        response = client.post(
            SETTINGS,
            {
                "organizers_email": "",
                "conference_timezone": "UTC",
                "schedule_step_minutes": "7",
                "default_premiere_location": "YOUTUBE",
            },
        )
        assert response.status_code == 200
        assert "schedule_step_minutes" in response.context["form"].errors
        row.refresh_from_db()
        assert row.schedule_step_minutes == 15

    def test_a_coarser_step_warns_of_slots_between_its_rows(self, client, conference):
        """From 5 to 15 minutes, a 10:05 slot is drawn in the 10:00 row with
        the slot before it. The step is saved; the organizer is told."""
        row = make_settings(conference, schedule_step_minutes=5)
        ten = datetime(2026, 12, 5, 10, 0, tzinfo=timezone.utc)
        for title, minute in (("First", 0), ("Second", 5)):
            make_slot(
                make_session(conference, title=title),
                start_utc=ten + timedelta(minutes=minute),
                end_utc=ten + timedelta(minutes=minute + 5),
            )
        client.force_login(lead_of_program())
        form = {
            "organizers_email": "",
            "conference_timezone": "UTC",
            "default_premiere_location": "YOUTUBE",
        }
        response = client.post(
            SETTINGS, {**form, "schedule_step_minutes": "15"}, follow=True
        )
        row.refresh_from_db()
        assert row.schedule_step_minutes == 15
        shown = [str(m) for m in response.context["messages"]]
        assert shown[1] == (
            "1 slot starts between two rows of the new 15-minute grid and is "
            "drawn in the row above: “Second” (10:05). Move it onto the "
            "grid, or pick a finer step."
        )
        response = client.post(
            SETTINGS, {**form, "schedule_step_minutes": "5"}, follow=True
        )
        assert [str(m) for m in response.context["messages"]] == [
            "Saved the speaker settings."
        ]

    def test_the_warning_names_three_slots_at_most(self, conference):
        make_settings(conference, schedule_step_minutes=1)
        ten = datetime(2026, 12, 5, 10, 0, tzinfo=timezone.utc)
        for minute in range(1, 6):
            make_slot(
                make_session(conference, title=f"At {minute}"),
                start_utc=ten + timedelta(minutes=minute),
                end_utc=ten + timedelta(minutes=minute + 1),
            )
        warning = off_grid_warning(conference, 15)
        assert warning.startswith("5 slots start between two rows")
        assert "are drawn in the row above" in warning
        assert "“At 3” (10:03) and 2 more." in warning
        assert off_grid_warning(conference, 1) is None

    def test_only_what_the_edition_uses(self, client, conference):
        make_settings(
            conference,
            event_format=EventFormat.IN_PERSON,
            recordings=Recordings.NONE,
        )
        client.force_login(lead_of_program())
        fields = client.get(SETTINGS).context["form"].fields
        assert "default_premiere_location" not in fields
        assert "default_video_length_limit_minutes" not in fields
        assert "media_for_speakers" not in fields and "auto_transcribe" not in fields

    def test_a_program_member_without_the_lead_set_is_refused(self, client, conference):
        make_settings(conference)
        member = on_team(
            User.objects.create_user(username="moe", email="moe@x.org"), "Program"
        )
        client.force_login(member)
        assert client.get(SETTINGS).status_code == 403


@pytest.mark.django_db
class TestAllowedWebsites:
    def test_add_and_remove_from_the_share_tab(self, client, conference):
        row = make_settings(conference)
        client.force_login(lead_of_program())
        client.post(ORIGINS, {"url": "https://2027.Example.org/"})
        assert row.api_origins == ["https://2027.example.org"]
        client.post(ORIGINS, {"url": "https://2027.example.org"})
        assert AllowedOrigin.objects.count() == 1
        page = client.get(SHARE).content.decode()
        assert "https://2027.example.org" in page and "Add website" in page
        client.post(ORIGINS, {"url": "not a website"})
        assert AllowedOrigin.objects.count() == 1
        client.post(ORIGINS, {"remove": AllowedOrigin.objects.get().pk})
        assert row.api_origins == []

    def test_a_bad_or_stale_removal_changes_nothing(self, client, conference):
        """A junk id was a server error, and a stale one reported "Removed"
        and logged a change that never happened."""
        make_settings(conference)
        client.force_login(lead_of_program())
        for junk in ("abc", "999999", "²"):
            response = client.post(ORIGINS, {"remove": junk}, follow=True)
            assert response.status_code == 200
            assert "That website is not on the list." in response.content.decode()
        assert not ActivityLog.objects.filter(
            action="program.allowed_origins_changed"
        ).exists()

    def test_only_whoever_publishes(self, client, conference):
        make_settings(conference)
        reader = on_team(
            User.objects.create_user(username="ria", email="ria@x.org"),
            "Proposal reviewers",
        )
        client.force_login(reader)
        assert client.post(ORIGINS, {"url": "https://a.example"}).status_code == 403
