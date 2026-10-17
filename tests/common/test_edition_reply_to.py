"""Replies go to the edition's reply-to address (a team inbox or a Google
Group), since the portal sends from a no-reply address."""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from common.send_emails import edition_reply_to, send_email
from portal.models import Conference
from speakers.emails import team_reply_to
from speakers.models import SpeakerSettings
from tests.speakers.factories import make_settings

GROUP = "summit-organizers@googlegroups.com"


def send(to, **kwargs):
    return send_email("Hello", to, markdown_template="emails/base_email.md", **kwargs)


@pytest.fixture
def grouped(conference):
    conference.reply_to_email = GROUP
    conference.save()
    return conference


@pytest.mark.django_db
class TestEditionReplyTo:
    def test_an_email_about_the_edition_replies_to_its_address(self, grouped):
        send(["a@x.org"], conference=grouped)
        assert mail.outbox[0].reply_to == [GROUP]
        assert mail.outbox[0].to == ["a@x.org"] and not mail.outbox[0].cc

    def test_an_email_about_no_edition_replies_to_the_active_one(self, grouped):
        send(["a@x.org"])
        assert mail.outbox[0].reply_to == [GROUP]

    def test_unset_falls_back_to_the_from_address(self, conference, settings):
        settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
        send(["a@x.org"], conference=conference)
        assert mail.outbox[0].reply_to == ["noreply@example.com"]

    def test_no_active_edition_falls_back_to_the_from_address(
        self, conference, settings
    ):
        Conference.objects.update(is_active=False)
        settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
        assert edition_reply_to() is None
        send(["a@x.org"])
        assert mail.outbox[0].reply_to == ["noreply@example.com"]

    def test_a_caller_supplied_reply_to_still_wins(self, grouped):
        send(["a@x.org"], conference=grouped, reply_to=["desk@example.com"])
        assert mail.outbox[0].reply_to == ["desk@example.com"]


@pytest.mark.django_db
class TestSpeakerTeamAddress:
    def test_the_speaker_team_address_wins_over_the_edition(self, grouped):
        make_settings(grouped)
        SpeakerSettings.objects.filter(conference=grouped).update(
            organizers_email="speakers@example.org"
        )
        assert team_reply_to(grouped) == ["speakers@example.org"]

    def test_a_blank_team_address_uses_the_edition(self, grouped):
        make_settings(grouped)
        SpeakerSettings.objects.filter(conference=grouped).update(organizers_email="")
        assert team_reply_to(grouped) == [GROUP]


@pytest.mark.django_db
class TestOtherSenders:
    def test_account_email_replies_to_the_active_edition(self, client, grouped):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=True
        )
        client.post(reverse("account_reset_password"), {"email": user.email})
        assert mail.outbox[0].reply_to == [GROUP]

    def test_account_email_without_one_keeps_allauths_default(self, client, conference):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=True
        )
        client.post(reverse("account_reset_password"), {"email": user.email})
        assert mail.outbox[0].reply_to == []


@pytest.mark.django_db
def test_the_edition_form_saves_the_reply_to_address(client, admin_user, grouped):
    """The field sits in its own "Email" group on the edition form."""
    client.force_login(admin_user)
    response = client.get(reverse("conference_edit", args=[grouped.pk]))
    assert b'name="reply_to_email"' in response.content
    assert grouped.reply_to == [GROUP]
