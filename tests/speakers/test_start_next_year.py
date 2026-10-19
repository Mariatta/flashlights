import pytest
from django.urls import reverse
from django.utils import timezone

from portal.models import ChatPlatform, Conference
from speakers.constants import EventFormat, Recordings
from speakers.models import (
    ChecklistTemplate,
    Handbook,
    ReadinessGate,
    SpeakerSettings,
    speaker_module_enabled,
)
from speakers.seeds import (
    DEFAULT_TEMPLATES,
    PERFORMER_NAME,
    clone_speaker_setup,
    seed_checklists,
)
from tests.ticketing_ids import make_ticketing
from ticketing.models import TicketingSettings

from .factories import make_settings


def payload(**overrides):
    data = {
        "year": 2027,
        "name": "Flashlights 2027",
        "slug": "2027",
        "cadence": "ONCE",
        "conference_date": "2027-05-01",
    }
    data.update(overrides)
    return data


@pytest.fixture
def source(conference):
    """The previous edition with a full speaker setup."""
    make_settings(
        conference,
        conference_timezone="Europe/Lisbon",
        event_format=EventFormat.HYBRID,
        organizers_email="team@example.com",
        translation_languages=["pt-br"],
    )
    make_ticketing(conference, organizer="flashlights")
    seed_checklists(conference)
    Handbook.objects.create(
        conference=conference,
        key="workshop",
        version=2,
        title="Workshop guide",
        url="https://example.org/w",
        published_at=timezone.now(),
    )
    Handbook.objects.create(
        conference=conference, key="speaker", version=1, title="Draft only"
    )
    return conference


@pytest.mark.django_db
class TestStartNextYear:
    def test_form_offers_the_speaker_options(self, client, admin_user, source):
        client.force_login(admin_user)
        content = client.get(reverse("start_new_year")).content.decode()
        assert "Copy the speaker portal setup" in content
        assert "Enable the speaker portal for this edition" in content

    def test_copies_setup_and_enables(self, client, admin_user, source):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            payload(copy_speaker_setup="on", speaker_portal="on"),
            follow=True,
        )
        content = response.content.decode()
        assert (
            f"{len(DEFAULT_TEMPLATES)} checklist template(s), 1 speaker guide(s)"
            in content
        )
        assert "The speaker portal is on." in content
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is True
        row = SpeakerSettings.objects.get(conference=new)
        assert row.conference_timezone == "Europe/Lisbon"
        assert row.event_format == EventFormat.HYBRID
        assert row.organizers_email == "team@example.com"
        assert row.translation_languages == ["pt-br"]
        # The ticketing comes along: same shop and maps, the
        # event slug the form gave.
        ticketing = TicketingSettings.objects.get(conference=new)
        assert ticketing.organizer == "flashlights"
        assert ticketing.api_token == "tok-secret"
        assert ticketing.question_map and ticketing.event_id == ""
        assert ChecklistTemplate.objects.filter(conference=new).count() == len(
            DEFAULT_TEMPLATES
        )
        guide = Handbook.objects.get(conference=new, key="workshop")
        assert guide.version == 1 and not guide.is_published
        assert guide.url == "https://example.org/w"
        assert not Handbook.objects.filter(conference=new, key="speaker").exists()

    def test_copies_the_recordings_setting(self, client, admin_user, conference):
        """In person with the team recording stays so: speakers pre-recording
        is a combination the edition form refuses in person."""
        make_settings(
            conference, event_format=EventFormat.IN_PERSON, recordings=Recordings.TEAM
        )
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload(copy_speaker_setup="on"))
        row = SpeakerSettings.objects.get(conference__year=2027)
        assert row.event_format == EventFormat.IN_PERSON
        assert row.recordings == Recordings.TEAM

    def test_keeps_the_community_chat(self, client, admin_user, conference):
        """A Zulip community's next edition does not go back to Discord."""
        conference.chat_platform = ChatPlatform.OTHER
        conference.chat_name = "Zulip"
        conference.chat_url = "https://example.zulipchat.com/"
        conference.save()
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload())
        new = Conference.objects.get(year=2027)
        assert new.chat_platform == ChatPlatform.OTHER
        assert new.chat_name == "Zulip"
        assert new.chat_url == "https://example.zulipchat.com/"

    def test_copy_without_enabling(self, client, admin_user, source):
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload(copy_speaker_setup="on"))
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is False
        assert SpeakerSettings.objects.filter(conference=new).exists()

    def test_enable_without_copy(self, client, admin_user, source):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"), payload(speaker_portal="on"), follow=True
        )
        new = Conference.objects.get(year=2027)
        assert speaker_module_enabled(new) is True
        # Nothing carried over, so the edition starts on the defaults.
        assert ChecklistTemplate.objects.filter(conference=new).exists()
        assert "checklist template" not in response.content.decode()

    def test_enable_without_copy_seeds_for_the_previous_format(
        self, client, admin_user, conference
    ):
        """An in-person community's new edition gets the in-person defaults:
        no tech check, no upload gate, no Performer template."""
        make_settings(
            conference, event_format=EventFormat.IN_PERSON, recordings=Recordings.TEAM
        )
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload(speaker_portal="on"))
        new = Conference.objects.get(year=2027)
        row = SpeakerSettings.objects.get(conference=new)
        assert row.event_format == EventFormat.IN_PERSON
        assert row.recordings == Recordings.TEAM
        gates = set(
            ReadinessGate.objects.filter(conference=new).values_list("code", flat=True)
        )
        assert "upload-open" not in gates and "tech-check-open" not in gates
        assert not ChecklistTemplate.objects.filter(
            conference=new, name=PERFORMER_NAME
        ).exists()

    def test_neither(self, client, admin_user, source):
        client.force_login(admin_user)
        client.post(reverse("start_new_year"), payload())
        new = Conference.objects.get(year=2027)
        assert not SpeakerSettings.objects.filter(conference=new).exists()

    def test_clone_is_idempotent_and_survives_missing_source_settings(self, conference):
        SpeakerSettings.objects.filter(conference=conference).delete()
        seed_checklists(conference)
        target = Conference.objects.create(year=2027, name="Next", slug="2027")
        first = clone_speaker_setup(target, conference)
        assert first == {
            "templates": len(DEFAULT_TEMPLATES),
            "items": first["items"],
            "guides": 0,
            "rooms": 0,
        }
        second = clone_speaker_setup(target, conference, enable=True)
        assert second["templates"] == 0 and second["guides"] == 0
        assert speaker_module_enabled(target) is True

    def test_existing_guide_key_in_target_is_kept(self, conference, source):
        target = Conference.objects.create(year=2027, name="Next", slug="2027")
        Handbook.objects.create(
            conference=target, key="workshop", version=1, title="Mine"
        )
        assert clone_speaker_setup(target, conference)["guides"] == 0
        assert Handbook.objects.get(conference=target, key="workshop").title == "Mine"
