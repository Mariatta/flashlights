"""The organizer's session form says who sees each field: what the speaker
edits, what they see but the team sets, and what is the team's alone."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import EventFormat, Recordings
from speakers.forms import SessionForm

from .factories import make_session, make_settings


def groups(conference):
    form = SessionForm(conference=conference)
    return form, {g["key"]: [f.name for f in g["fields"]] for g in form.field_groups()}


@pytest.mark.django_db
class TestFieldGroups:
    @pytest.mark.parametrize(
        "fmt,mode",
        [
            (EventFormat.ONLINE, Recordings.SPEAKERS),
            (EventFormat.IN_PERSON, Recordings.TEAM),
            (EventFormat.HYBRID, Recordings.NONE),
        ],
    )
    def test_every_field_is_in_exactly_one_group(self, conference, fmt, mode):
        make_settings(conference, event_format=fmt, recordings=mode)
        form, by_key = groups(conference)
        grouped = [name for names in by_key.values() for name in names]
        assert sorted(grouped) == sorted(form.fields)

    def test_the_video_fields_are_the_teams(self, conference):
        make_settings(conference)
        _, by_key = groups(conference)
        assert {"youtube_url", "youtube_publish_at", "notes_md"} <= set(
            by_key["team_only"]
        )
        assert "title" in by_key["speaker_edits"]
        assert "video_length_limit_minutes" in by_key["speaker_sees"]

    def test_team_recording_has_no_video_limit(self, conference):
        make_settings(conference, recordings=Recordings.TEAM)
        form, _ = groups(conference)
        assert "video_length_limit_minutes" not in form.fields
        assert "youtube_url" in form.fields

    def test_the_page_marks_the_team_only_group(self, client, conference):
        make_settings(conference)
        organizer = User.objects.create_user(username="org", is_staff=True)
        client.force_login(organizer)
        session = make_session(conference)
        page = client.get(reverse("speakers:session_edit", args=[session.slug]))
        content = page.content.decode()
        assert "Team only: never shown to the speaker" in content
        assert "The speaker sees and can edit" in content
