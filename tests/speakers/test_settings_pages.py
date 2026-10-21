"""Organizers open session proposals and list the websites that may
show the program in the portal, not the Django admin."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import EventFormat, Recordings
from speakers.models import ActivityLog, AllowedOrigin, SpeakerSettings
from tests.grants import on_team

from .factories import make_settings

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
                "default_premiere_location": "YOUTUBE",
                "default_video_length_limit_minutes": "20",
                "media_for_speakers": "on",
            },
        )
        assert response.status_code == 302
        row = SpeakerSettings.objects.get(conference=conference)
        assert row.proposals_open and row.conference_timezone == "America/Los_Angeles"
        assert ActivityLog.objects.filter(action="speakers.settings_changed").exists()

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
