"""Volunteer emails follow the edition's chat: Discord lines only on a
Discord edition, the edition's own invite link, nothing for no chat."""

import pytest
from django.core import mail

from portal.models import ChatPlatform
from tests.grants import on_team
from volunteer.constants import ApplicationStatus
from volunteer.models import (
    Team,
    VolunteerProfile,
    send_internal_volunteer_onboarding_email,
    send_volunteer_cancelled_emails,
    send_volunteer_onboarding_email,
)


def applicant(conference, portal_user, **chat):
    for name, value in chat.items():
        setattr(conference, name, value)
    conference.save()
    profile = VolunteerProfile(user=portal_user, conference=conference)
    profile.discord_username = "mydiscord"
    profile.github_username = "mygithub"
    profile.save()  # sends the application email
    return profile, mail.outbox[-1].body


@pytest.mark.django_db
class TestApplicationEmail:
    def test_no_chat_mentions_no_chat(self, conference, portal_user):
        _, body = applicant(conference, portal_user, chat_platform=ChatPlatform.NONE)
        assert "Discord" not in body and "mydiscord" not in body
        assert "join us on" not in body

    def test_another_platform_links_its_invite(self, conference, portal_user):
        _, body = applicant(
            conference,
            portal_user,
            chat_platform=ChatPlatform.OTHER,
            chat_name="Zulip",
            chat_url="https://chat.example.org/join",
        )
        assert "Discord" not in body
        assert "Zulip" in body and "https://chat.example.org/join" in body

    def test_discord_without_a_link_asks_the_team_lead(self, conference, portal_user):
        _, body = applicant(
            conference, portal_user, chat_platform=ChatPlatform.DISCORD, chat_url=""
        )
        assert "mydiscord" in body
        assert "join us on Discord; your team lead sends the invitation" in body
        assert "2fUN4ddVfP" not in body


@pytest.mark.django_db
class TestOnboardingEmails:
    def onboard(self, conference, portal_user, **chat):
        profile, _ = applicant(conference, portal_user, **chat)
        team = Team.objects.create(
            short_name="Program", description="d", conference=conference
        )
        profile.teams.add(team)
        # On the Organizers team, so the core organizers' part is in too.
        profile.application_status = ApplicationStatus.APPROVED
        profile.save(update_fields=["application_status"])
        on_team(portal_user)
        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        send_internal_volunteer_onboarding_email(profile)
        assert mail.outbox
        return " ".join(m.body for m in mail.outbox)

    def test_no_chat(self, conference, portal_user):
        body = self.onboard(conference, portal_user, chat_platform=ChatPlatform.NONE)
        assert "Discord" not in body and "Jelly" not in body

    def test_another_platform(self, conference, portal_user):
        body = self.onboard(
            conference,
            portal_user,
            chat_platform=ChatPlatform.OTHER,
            chat_name="Slack",
            chat_url="https://slack.example.org",
        )
        assert "Discord" not in body
        assert "Join Slack" in body and "https://slack.example.org" in body

    def test_discord(self, conference, portal_user):
        """The default platform: the Discord lines are there."""
        body = self.onboard(conference, portal_user, chat_platform=ChatPlatform.DISCORD)
        assert "Grant them the Volunteer role on Discord." in body
        assert "Their Discord username is: mydiscord" in body
        assert "The Organizer role on Discord" in body


@pytest.mark.django_db
class TestTeamLeadCancellationNotice:
    """The lead is told what to take back, following the edition's chat."""

    def notice(self, conference, portal_user, django_user_model, **chat):
        profile, _ = applicant(conference, portal_user, **chat)
        team = Team.objects.create(
            short_name="Program", description="d", conference=conference
        )
        lead = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user(
                username="lead", email="lead@example.com"
            ),
            conference=conference,
        )
        team.team_leads.add(lead)
        mail.outbox.clear()
        send_volunteer_cancelled_emails(profile, [team])
        return next(m.body for m in mail.outbox if m.to == ["lead@example.com"])

    def test_the_github_line_names_the_github_username(
        self, conference, portal_user, django_user_model
    ):
        body = self.notice(
            conference, portal_user, django_user_model, chat_platform=ChatPlatform.NONE
        )
        assert "GitHub: mygithub" in body
        assert "mydiscord" not in body

    def test_discord(self, conference, portal_user, django_user_model):
        body = self.notice(
            conference,
            portal_user,
            django_user_model,
            chat_platform=ChatPlatform.DISCORD,
        )
        assert "Discord: mydiscord" in body
        assert "Remove the Volunteer role on Discord." in body

    def test_another_platform(self, conference, portal_user, django_user_model):
        body = self.notice(
            conference,
            portal_user,
            django_user_model,
            chat_platform=ChatPlatform.OTHER,
            chat_name="Zulip",
            chat_url="https://chat.example.org/join",
        )
        assert "Discord" not in body
        assert "Remove them from Zulip." in body

    def test_no_chat(self, conference, portal_user, django_user_model):
        body = self.notice(
            conference, portal_user, django_user_model, chat_platform=ChatPlatform.NONE
        )
        assert "Discord" not in body and "Remove them from" not in body


@pytest.mark.django_db
class TestOnboardingWording:
    def test_no_roles_no_heading_and_no_drive_without_a_folder(
        self, conference, portal_user, settings
    ):
        settings.GDRIVE_FOLDER_ID = ""
        profile, _ = applicant(conference, portal_user)
        profile.application_status = ApplicationStatus.APPROVED
        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        body = mail.outbox[0].body
        assert "Role Assignment" not in body
        assert "GitHub" not in body and "shared drive" not in body
        assert "are no longer able to volunteer" in body

    def test_the_drive_is_a_link_for_core_organizers(
        self, conference, portal_user, settings
    ):
        settings.GDRIVE_FOLDER_ID = "abc123"
        profile, _ = applicant(conference, portal_user)
        profile.application_status = ApplicationStatus.APPROVED
        profile.save(update_fields=["application_status"])
        on_team(portal_user)
        mail.outbox.clear()
        send_volunteer_onboarding_email(profile)
        assert "https://drive.google.com/drive/folders/abc123" in mail.outbox[0].body
