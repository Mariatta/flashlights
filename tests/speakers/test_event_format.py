"""An in-person edition leaves out the online-only
parts of the module (pre-recorded delivery, premieres, the tech check and
the upload gate); online and hybrid editions keep everything."""

import io

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from portal.models import ChatPlatform
from speakers.admin import SpeakerSettingsAdmin
from speakers.board import build_post_production_board
from speakers.checklists import instantiate_session_checklist
from speakers.constants import (
    ChecklistScope,
    Delivery,
    EventFormat,
    MediaKind,
    Recordings,
)
from speakers.directory import data_columns, write_presenters_csv
from speakers.forms import (
    ChecklistTemplateForm,
    PresenterForm,
    ProposalProfileForm,
    SessionForm,
    SessionTypeForm,
    SpeakerProfileForm,
)
from speakers.media import can_upload
from speakers.models import (
    ChecklistTemplate,
    ReadinessGate,
    SessionType,
    SpeakerSettings,
    event_format,
    is_in_person,
    recordings,
    records_sessions,
    speakers_pre_record,
    team_records,
)
from speakers.program_types import (
    DEFAULT_SESSION_TYPES,
    seed_program_types,
    session_type,
)
from speakers.seeds import (
    DEFAULT_TEMPLATES,
    DISCORD_ROLE_TITLE,
    PERFORMER_NAME,
    RECORDED_SESSION_NAME,
    seed_checklists,
)
from volunteer.forms import VolunteerProfileForm

from .factories import add_presenter, make_presenter, make_session, make_settings


@pytest.fixture
def in_person(conference):
    return make_settings(
        conference, event_format=EventFormat.IN_PERSON, recordings=Recordings.TEAM
    )


#: The defaults carry the pre-recording pipeline: its performer and
#: post-production templates and the upload gate.
PRE_RECORD_TEMPLATES = 2


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
        # Every default but the pre-recorded performance, which needs
        # speakers who pre-record.
        assert types.count() == len(DEFAULT_SESSION_TYPES) - 1
        assert not types.filter(code="PERFORMANCE").exists()
        assert set(types.values_list("default_delivery", flat=True)) == {Delivery.LIVE}

    def test_no_gates_no_tech_check_no_video_templates(self, conference, in_person):
        result = seed_checklists(conference)
        assert ReadinessGate.objects.filter(conference=conference).count() == 0
        reasons = {reason for _, reason in result.skipped}
        assert reasons == {"speakers do not pre-record in this edition"}
        skipped = {name for name, _ in result.skipped}
        assert PERFORMER_NAME in skipped
        # Minus the two pre-record templates, plus the recorded-session
        # template, since the team records.
        assert result.templates == len(DEFAULT_TEMPLATES) - PRE_RECORD_TEMPLATES + 1
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        titles = set(general.items.values_list("title", flat=True))
        assert "Do a tech check" not in titles
        assert "Tell us what you need in the room" in titles
        register = general.items.get(title="Register for the event")
        assert "attendee list" in register.description_md
        # Seeding again adds nothing.
        again = seed_checklists(conference)
        assert (again.templates, again.items) == (0, 0)

    def test_hybrid_asks_about_the_room_and_the_tech_check(self, conference):
        make_settings(conference, event_format=EventFormat.HYBRID)
        seed_checklists(conference)
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        titles = list(general.items.values_list("title", flat=True))
        assert "Tell us what you need in the room" in titles
        assert "Do a tech check" in titles
        assert titles.index("Tell us what you need in the room") < titles.index(
            "Do a tech check"
        )

    def test_online_edition_keeps_everything(self, conference):
        make_settings(conference, event_format=EventFormat.ONLINE)
        result = seed_checklists(conference)
        assert result.skipped == []
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        titles = set(general.items.values_list("title", flat=True))
        assert "Tell us what you need in the room" not in titles
        assert "Do a tech check" in titles
        assert ReadinessGate.objects.filter(conference=conference).count() == 2
        # The team's recording template is not seeded when speakers pre-record.
        assert not conference.checklist_templates.filter(
            name=RECORDED_SESSION_NAME
        ).exists()


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


@pytest.mark.django_db
class TestRecordings:
    def test_helpers_default_to_speakers_pre_recording(self, conference):
        assert recordings(None) == Recordings.SPEAKERS
        assert recordings(conference) == Recordings.SPEAKERS
        assert speakers_pre_record(conference) and records_sessions(conference)
        assert team_records(conference) is False
        make_settings(conference, recordings=Recordings.NONE)
        assert records_sessions(conference) is False

    def test_session_form_without_recordings_has_no_video_fields(self, conference):
        make_settings(conference, recordings=Recordings.NONE)
        form = SessionForm(conference=conference)
        for field in (
            "youtube_url",
            "youtube_publish_at",
            "video_length_limit_minutes",
        ):
            assert field not in form.fields

    def test_team_recording_lets_a_live_session_carry_its_video_link(
        self, conference, in_person
    ):
        form = SessionForm(
            conference=conference,
            data={
                "kind": session_type(conference, "TALK").pk,
                "title": "Talk",
                "youtube_url": "https://youtube.com/watch?v=x",
                "youtube_publish_at": "2026-06-01T10:00",
            },
        )
        assert form.is_valid(), form.errors
        # The limit is about a speaker's upload, so the form does not offer
        # it when the team records; the link stays.
        assert "video_length_limit_minutes" not in form.fields

    def test_seeds_for_the_team_recording(self, conference, in_person):
        seed_checklists(conference)
        template = conference.checklist_templates.get(name=RECORDED_SESSION_NAME)
        assert template.scope == ChecklistScope.SESSION
        assert template.kind is None and template.delivery == Delivery.LIVE
        titles = list(template.items.values_list("title", flat=True))
        assert titles[0] == "Upload the recording"
        assert titles[-1] == "Publish the recording with its transcript"
        # Content presenters get a review line; hosts do not.
        talk = conference.checklist_templates.get(name="Talk presenter")
        assert talk.items.filter(title="Review your recording").exists()
        host = conference.checklist_templates.get(name="Opening host")
        assert not host.items.filter(title="Review your recording").exists()
        # No gates at all: no tech check in person, no upload when the team records.
        assert ReadinessGate.objects.filter(conference=conference).count() == 0

    def test_no_recordings_seeds_no_pipeline(self, conference):
        make_settings(conference, recordings=Recordings.NONE)
        result = seed_checklists(conference)
        names = set(conference.checklist_templates.values_list("name", flat=True))
        assert RECORDED_SESSION_NAME not in names and PERFORMER_NAME not in names
        assert not conference.checklist_templates.filter(
            scope=ChecklistScope.SESSION
        ).exists()
        assert len(result.skipped) == PRE_RECORD_TEMPLATES
        # The tech check is still an online line; the upload gate is not seeded.
        assert list(
            ReadinessGate.objects.filter(conference=conference).values_list(
                "code", flat=True
            )
        ) == ["tech-check-open"]

    def test_a_kindless_session_template_applies_to_every_kind(
        self, conference, in_person
    ):
        seed_checklists(conference)
        generic = conference.checklist_templates.get(name=RECORDED_SESSION_NAME)
        talk = make_session(conference, kind="TALK")
        assert ChecklistTemplate.for_session(talk) == generic
        # A template naming the kind wins over the generic one.
        specific = ChecklistTemplate.objects.create(
            conference=conference,
            scope=ChecklistScope.SESSION,
            name="Talk, recorded",
            kind=talk.kind,
            delivery=Delivery.LIVE,
        )
        assert ChecklistTemplate.for_session(talk) == specific
        # The model accepts a session template with no kind, and still
        # wants one on a presenter template.
        generic.full_clean()
        with pytest.raises(ValidationError):
            ChecklistTemplate(
                conference=conference,
                scope=ChecklistScope.PRESENTER,
                name="No kind",
                role=talk.kind.default_role,
            ).full_clean()

    def test_board_rows_follow_the_recordings_setting(self, conference, admin_user):
        row = make_settings(conference, recordings=Recordings.TEAM)
        seed_checklists(conference)
        talk = make_session(conference, kind="TALK")
        add_presenter(talk, make_presenter(conference))
        instantiate_session_checklist(talk)
        board = build_post_production_board(conference, admin_user)
        assert [r["session"] for r in board["rows"]] == [talk]
        row.recordings = Recordings.NONE
        row.save()
        assert build_post_production_board(conference, admin_user)["rows"] == []
        row.recordings = Recordings.SPEAKERS
        row.save()
        assert build_post_production_board(conference, admin_user)["rows"] == []

    def test_speakers_upload_only_when_they_pre_record(self, conference, portal_user):
        row = make_settings(conference, recordings=Recordings.TEAM)
        talk = make_session(conference, kind="TALK")
        link = add_presenter(talk, make_presenter(conference, user=portal_user))
        link.confirm()
        assert can_upload(portal_user, talk, MediaKind.RAW_VIDEO) is False
        row.recordings = Recordings.SPEAKERS
        row.save()
        assert can_upload(portal_user, talk, MediaKind.RAW_VIDEO) is True

    def test_pages_hide_the_files_tab_without_recordings(
        self, client, admin_user, conference
    ):
        make_settings(conference, recordings=Recordings.NONE)
        talk = make_session(conference, kind="TALK")
        client.force_login(admin_user)
        content = client.get(talk.get_absolute_url()).content.decode()
        assert 'id="tab-files-link"' not in content
        content = client.get(reverse("speakers:checklist_board")).content.decode()
        assert "tab=post_production" not in content

    def test_admin_hides_media_without_recordings(self, conference):
        row = make_settings(conference, recordings=Recordings.NONE)
        model_admin = SpeakerSettingsAdmin(SpeakerSettings, AdminSite())
        request = RequestFactory().get("/")
        titles = [title for title, _ in model_admin.get_fieldsets(request, row)]
        assert "Media" not in titles


@pytest.mark.django_db
class TestCommunityChat:
    def _general_titles(self, conference):
        seed_checklists(conference)
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        return list(general.items.values_list("title", flat=True))

    def test_discord_edition_asks_and_seeds_as_before(self, conference):
        assert conference.uses_discord and conference.chat_label == "Discord"
        titles = self._general_titles(conference)
        assert "Join the event Discord" in titles and DISCORD_ROLE_TITLE in titles
        assert "discord_username" in PresenterForm(conference=conference).fields
        assert "Discord" in [h for h, _ in data_columns(conference)]

    def test_another_platform_gets_its_own_line_and_no_discord(self, conference):
        conference.chat_platform = ChatPlatform.OTHER
        conference.chat_name = "Zulip"
        conference.chat_url = "https://chat.example.org/join"
        conference.save()
        assert conference.chat_label == "Zulip"
        titles = self._general_titles(conference)
        assert "Join the event chat on Zulip" in titles
        assert "Join the event Discord" not in titles
        assert DISCORD_ROLE_TITLE not in titles
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        line = general.items.get(title="Join the event chat on Zulip")
        assert "https://chat.example.org/join" in line.description_md
        for form in (
            PresenterForm(conference=conference),
            ProposalProfileForm(conference=conference),
            SpeakerProfileForm(instance=make_presenter(conference)),
        ):
            assert "discord_username" not in form.fields
            assert form.shared_discord_username == ""
        assert "Discord" not in [h for h, _ in data_columns(conference)]
        out = write_presenters_csv([], io.StringIO(), conference).getvalue()
        assert "Discord" not in out

    def test_no_chat_seeds_no_line(self, conference):
        conference.chat_platform = ChatPlatform.NONE
        conference.save()
        assert conference.has_chat is False
        titles = self._general_titles(conference)
        assert not [t for t in titles if "chat" in t.lower() or "Discord" in t]

    def test_discord_line_carries_the_invite_link(self, conference):
        conference.chat_url = "https://discord.gg/example"
        conference.save()
        seed_checklists(conference)
        general = conference.checklist_templates.get(scope=ChecklistScope.GENERAL)
        line = general.items.get(title="Join the event Discord")
        assert "https://discord.gg/example" in line.description_md

    def test_presenter_pages_hide_discord_off_discord(
        self, client, admin_user, conference
    ):
        make_settings(conference)
        presenter = make_presenter(conference, discord_username="ada_l")
        client.force_login(admin_user)
        content = client.get(presenter.get_absolute_url()).content.decode()
        assert "Discord:" in content
        listing = client.get(reverse("speakers:presenter_list")).content.decode()
        assert "Discord" in listing
        conference.chat_platform = ChatPlatform.NONE
        conference.save()
        content = client.get(presenter.get_absolute_url()).content.decode()
        assert "Discord:" not in content
        listing = client.get(reverse("speakers:presenter_list")).content.decode()
        assert "Discord" not in listing
        csv = client.get(reverse("speakers:presenter_data_csv")).content.decode()
        assert "Discord" not in csv

    def test_volunteer_form_asks_for_discord_only_on_discord(
        self, conference, portal_user
    ):
        assert (
            VolunteerProfileForm(user=portal_user).fields["discord_username"].required
        )
        conference.chat_platform = ChatPlatform.OTHER
        conference.chat_name = "Slack"
        conference.save()
        assert "discord_username" not in VolunteerProfileForm(user=portal_user).fields

    def test_edition_form_wants_a_name_for_another_platform(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": ChatPlatform.OTHER,
                "chat_url": "https://chat.example.org/",
            },
        )
        assert "Name the platform" in response.content.decode()
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": ChatPlatform.OTHER,
                "chat_name": "Zulip",
                "chat_url": "https://chat.example.org/",
            },
        )
        conference.refresh_from_db()
        assert conference.chat_label == "Zulip"
        assert conference.chat_url == "https://chat.example.org/"
