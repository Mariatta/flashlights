"""Decision 0013, stage b: an in-person edition leaves out the online-only
parts of the module (pre-recorded delivery, premieres, the tech check and
the upload gate); online and hybrid editions keep everything."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from speakers.admin import SpeakerSettingsAdmin
from speakers.constants import ChecklistScope, Delivery, EventFormat
from speakers.forms import ChecklistTemplateForm, SessionForm, SessionTypeForm
from speakers.models import (
    ReadinessGate,
    SessionType,
    SpeakerSettings,
    event_format,
    is_in_person,
)
from speakers.program_types import (
    DEFAULT_SESSION_TYPES,
    seed_program_types,
    session_type,
)
from speakers.seeds import DEFAULT_TEMPLATES, PERFORMER_NAME, seed_checklists

from .factories import make_settings


@pytest.fixture
def in_person(conference):
    return make_settings(conference, event_format=EventFormat.IN_PERSON)


@pytest.mark.django_db
class TestHelpers:
    def test_online_without_an_edition_or_a_row(self, conference):
        assert event_format(None) == EventFormat.ONLINE
        assert event_format(conference) == EventFormat.ONLINE
        assert is_in_person(conference) is False

    def test_reads_the_row(self, conference):
        make_settings(conference, event_format=EventFormat.HYBRID)
        assert event_format(conference) == EventFormat.HYBRID
        assert is_in_person(conference) is False
        SpeakerSettings.objects.filter(conference=conference).update(
            event_format=EventFormat.IN_PERSON
        )
        assert is_in_person(conference) is True


@pytest.mark.django_db
class TestForms:
    def test_session_form_has_no_delivery_and_saves_live(self, conference, in_person):
        form = SessionForm(
            conference=conference,
            data={"kind": session_type(conference, "TALK").pk, "title": "Talk"},
        )
        assert "delivery" not in form.fields
        assert "premiere_location" not in form.fields
        assert form.is_valid(), form.errors
        session = form.save()
        assert session.delivery == Delivery.LIVE

    def test_session_form_keeps_the_choice_for_hybrid(self, conference):
        make_settings(conference, event_format=EventFormat.HYBRID)
        form = SessionForm(conference=conference)
        assert "delivery" in form.fields and "premiere_location" in form.fields

    def test_type_form_has_no_default_delivery(self, conference, in_person):
        form = SessionTypeForm(
            conference=conference,
            data={
                "name": "Fireside",
                "code": "FIRESIDE",
                "is_content": "on",
                "default_duration_minutes": 20,
                "sort_order": 50,
                "is_active": "on",
            },
        )
        assert "default_delivery" not in form.fields
        assert form.is_valid(), form.errors
        assert form.save().default_delivery == Delivery.LIVE

    def test_template_form_has_no_delivery_and_session_scope_is_live(
        self, conference, in_person
    ):
        talk = session_type(conference, "TALK")
        form = ChecklistTemplateForm(
            conference=conference,
            data={
                "scope": ChecklistScope.SESSION,
                "name": "Talk, the room",
                "kind": talk.pk,
                "is_active": "on",
            },
        )
        assert "delivery" not in form.fields
        assert form.is_valid(), form.errors
        assert form.save().delivery == Delivery.LIVE
        # A presenter template still carries no delivery.
        form = ChecklistTemplateForm(
            conference=conference,
            data={
                "scope": ChecklistScope.PRESENTER,
                "name": "Talk presenter, the room",
                "kind": talk.pk,
                "role": talk.default_role.pk,
                "is_active": "on",
            },
        )
        assert form.is_valid(), form.errors
        assert form.save().delivery == ""


@pytest.mark.django_db
class TestSeeds:
    def test_every_default_type_is_live(self, conference, in_person):
        seed_program_types(conference)
        types = SessionType.objects.filter(conference=conference)
        assert types.count() == len(DEFAULT_SESSION_TYPES)
        assert set(types.values_list("default_delivery", flat=True)) == {Delivery.LIVE}

    def test_no_gates_no_tech_check_no_video_templates(self, conference, in_person):
        result = seed_checklists(conference)
        assert ReadinessGate.objects.filter(conference=conference).count() == 0
        assert [reason for _, reason in result.skipped] == ["online editions only"] * 2
        skipped = {name for name, _ in result.skipped}
        assert PERFORMER_NAME in skipped
        assert result.templates == len(DEFAULT_TEMPLATES) - 2
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        titles = set(general.items.values_list("title", flat=True))
        assert "Do a tech check" not in titles
        assert "Register for the event" in titles
        # Seeding again adds nothing.
        again = seed_checklists(conference)
        assert (again.templates, again.items) == (0, 0)

    def test_online_edition_keeps_everything(self, conference):
        make_settings(conference, event_format=EventFormat.ONLINE)
        result = seed_checklists(conference)
        assert result.skipped == []
        assert ReadinessGate.objects.filter(conference=conference).count() == 2


@pytest.mark.django_db
class TestAdmin:
    def _fields(self, row):
        model_admin = SpeakerSettingsAdmin(SpeakerSettings, AdminSite())
        request = RequestFactory().get("/")
        return [
            f
            for _, options in model_admin.get_fieldsets(request, row)
            for f in options["fields"]
        ]

    def test_in_person_row_hides_the_online_only_settings(self, conference, in_person):
        fields = self._fields(in_person)
        assert "default_premiere_location" not in fields
        assert "default_video_length_limit_minutes" not in fields
        assert "event_format" in fields and "program_visibility" in fields

    def test_other_rows_and_the_add_form_show_them(self, conference):
        row = make_settings(conference, event_format=EventFormat.HYBRID)
        assert "default_premiere_location" in self._fields(row)
        assert "default_premiere_location" in self._fields(None)
