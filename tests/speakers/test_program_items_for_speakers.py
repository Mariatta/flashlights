"""Program items (the keynote, the social) go public with the schedule
itself, so a speaker's schedule and dashboard treat them as public too."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import SessionStatus
from speakers.schedule import presenter_schedule

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_session,
    make_settings,
    make_slot,
)

T0 = datetime(2027, 5, 15, 17, 0, tzinfo=timezone.utc)


def placed(session, start):
    make_slot(session, start_utc=start)
    make_published_slot(session)
    session.schedule()
    return session


@pytest.fixture
def program(conference):
    make_settings(conference)
    user = User.objects.create_user(username="dana", email="dana@example.org")
    dana = make_presenter(conference, user=user, display_name="Dana")
    keynote = make_session(conference, kind="KEYNOTE", title="Keynote")
    add_presenter(keynote, dana, confirmed=True)
    keynote.confirm()
    placed(keynote, T0)
    social = make_session(
        conference, kind="SOCIAL", title="Social", status=SessionStatus.CONFIRMED
    )
    placed(social, T0 + timedelta(hours=6))
    return dana, keynote, social


@pytest.mark.django_db
class TestProgramItems:
    def test_on_the_schedule_and_not_a_draft(self, conference, program):
        dana, keynote, social = program
        entries = [
            e for day in presenter_schedule(conference, dana) for e in day["entries"]
        ]
        by_title = {e["session"].title: e for e in entries}
        assert set(by_title) == {"Keynote", "Social"}
        assert not by_title["Keynote"]["is_draft"]
        assert keynote.goes_public and social.goes_public

    def test_the_dashboard_does_not_call_the_keynote_unpublished(self, client, program):
        dana, _, _ = program
        client.force_login(dana.user)
        page = client.get(reverse("speakers:my_dashboard")).content.decode()
        assert "Keynote" in page and "Not yet public" not in page
