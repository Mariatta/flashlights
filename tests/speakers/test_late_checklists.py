"""Checklists written after people were accepted still reach them: an
organizer who approves the first proposals before loading the defaults,
or who adds a template later, should not leave anyone without a to-do."""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from speakers.checklists import apply_new_template_item
from speakers.constants import ChecklistScope, NoticeKind, SessionStatus
from speakers.models import ChecklistItem
from speakers.seeds import seed_checklists
from speakers.services import approve_proposal
from tests.grants import on_team

from .factories import (
    add_presenter,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
)
from .test_checklist_templates import make_item, make_template


@pytest.fixture
def approved(conference):
    """A proposal approved while the edition had no checklist templates."""
    make_settings(conference, proposals_open=True)
    session = make_session(conference, kind="TALK", status=SessionStatus.PROPOSED)
    presenter = make_presenter(conference)
    add_presenter(session, presenter)
    approve_proposal(make_proposal(session, presenter))
    assert not ChecklistItem.objects.filter(presenter=presenter).exists()
    return presenter


@pytest.mark.django_db
class TestLoadDefaultsAfterApproval:
    def test_the_speaker_gets_the_lines(self, approved, conference):
        result = seed_checklists(conference)
        items = ChecklistItem.objects.filter(presenter=approved)
        assert result.reached == items.count() > 0
        assert all(item.pending_notice == NoticeKind.NEW for item in items)
        # Loading again adds nothing more.
        assert seed_checklists(conference).reached == 0

    def test_the_button_says_so(self, client, approved, settings):
        settings.DEBUG = True  # the button is a local tool
        organizer = on_team(User.objects.create_user(username="org"))
        client.force_login(organizer)
        page = client.post(reverse("speakers:template_seed"), follow=True)
        assert "checklists of speakers already accepted" in page.content.decode()


@pytest.mark.django_db
class TestSessionLinesAddedLater:
    def test_a_confirmed_session_gets_a_new_session_template(self, conference):
        make_settings(conference)
        confirmed = make_session(conference, status=SessionStatus.CONFIRMED)
        draft = make_session(conference, status=SessionStatus.DRAFT)
        template = make_template(
            conference,
            scope=ChecklistScope.SESSION,
            name="Room setup",
            delivery=confirmed.delivery,
        )
        created = apply_new_template_item(make_item(template, title="Book the room"))
        assert [item.session for item in created] == [confirmed]
        assert not ChecklistItem.objects.filter(session=draft).exists()

    def test_matching_sessions_costs_the_same_however_many_there_are(self, conference):
        """Adding a line reads the edition's session templates once, not
        once per confirmed session."""
        make_settings(conference)
        template = make_template(
            conference, scope=ChecklistScope.SESSION, name="Workshop room"
        )

        def queries_with(count):
            for _ in range(count):
                make_session(conference, kind="TALK", status=SessionStatus.CONFIRMED)
            with CaptureQueriesContext(connection) as queries:
                apply_new_template_item(make_item(template, title=f"Line {count}"))
            return len(queries)

        assert queries_with(5) == queries_with(10)
