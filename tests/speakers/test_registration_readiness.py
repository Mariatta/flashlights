"""Setting up ticketing frees the speakers' "register" lines at once,
rather than at the nightly refresh."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from speakers.constants import ReadyRule, SessionStatus
from speakers.models import ChecklistItem
from speakers.seeds import seed_checklists
from speakers.services import approve_proposal
from ticketing.models import Provider, TicketingSettings

from .factories import (
    add_presenter,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
)


@pytest.mark.django_db
def test_ticketing_set_up_frees_the_register_line(conference):
    make_settings(conference, proposals_open=True)
    TicketingSettings.objects.filter(conference=conference).delete()
    seed_checklists(conference)
    session = make_session(conference, kind="TALK", status=SessionStatus.PROPOSED)
    presenter = make_presenter(conference)
    add_presenter(session, presenter)
    approve_proposal(make_proposal(session, presenter))
    register = ChecklistItem.objects.get(
        presenter=presenter, ready_rule=ReadyRule.REGISTRATION_OPEN
    )
    assert register.is_waiting
    TicketingSettings.objects.create(conference=conference, provider=Provider.CSV)
    register.refresh_from_db()
    assert not register.is_waiting


@pytest.mark.django_db
def test_a_poll_saving_its_sync_time_rechecks_nothing(conference):
    """Every edition's poll saves ``last_synced_at``; that moves no line."""
    make_settings(conference)
    seed_checklists(conference)
    ticketing = TicketingSettings.objects.create(
        conference=conference, provider=Provider.CSV
    )
    ticketing.last_synced_at = timezone.now()
    with CaptureQueriesContext(connection) as queries:
        ticketing.save(update_fields=["last_synced_at", "modified_date"])
    assert not [q for q in queries if "speakers_checklistitem" in q["sql"]]
