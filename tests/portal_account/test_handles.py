"""A person's handles kept once on the account: the catalogue, the record,
the copies on the role rows and the account form."""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from portal_account.forms import PortalProfileForm
from portal_account.handles import (
    CHANNELS,
    adopt_role_handles,
    clean_handle,
    handles_from_roles,
    handles_of,
    pronouns_of,
    push_handles,
    save_handles,
    save_pronouns,
)
from portal_account.models import Handle, PortalProfile
from speakers.models import Presenter
from volunteer.models import VolunteerProfile

migration = importlib.import_module(
    "portal_account.migrations.0005_flashlights_handles"
)


@pytest.mark.parametrize(
    "code, given, stored",
    [
        ("website", "example.org/me", "https://example.org/me"),
        ("github", "ada-l", "ada-l"),
        ("discord", "ada_l", "ada_l"),
        ("mastodon", "@ada@fosstodon.org", "https://fosstodon.org/@ada"),
        ("mastodon", "https://fosstodon.org/@ada", "https://fosstodon.org/@ada"),
        ("bluesky", "ada.bsky.social", "ada.bsky.social"),
        ("linkedin", "linkedin.com/in/ada", "https://linkedin.com/in/ada"),
        ("instagram", "ada.l", "ada.l"),
        ("x", "ada_l", "ada_l"),
        ("x", "  ", ""),
    ],
)
def test_each_channel_is_checked_and_stored_in_its_form(code, given, stored):
    assert clean_handle(code, given) == stored


@pytest.mark.parametrize(
    "code, given, message",
    [
        ("website", "not a site", "valid URL"),
        ("github", "-ada", "hyphen"),
        ("discord", "a", "between 2 and 32"),
        ("mastodon", "ada@fosstodon.org", "Mastodon"),
        ("bluesky", "-ada", "Bluesky"),
        ("linkedin", "example.org/ada", "LinkedIn"),
        ("instagram", "ada!", "Instagram"),
        ("x", "a" * 16, "X/Twitter"),
        ("mastodon", "https://" + "a" * 95 + ".org/@ada", "At most 100"),
    ],
)
def test_a_bad_value_says_why(code, given, message):
    with pytest.raises(ValidationError, match=message):
        clean_handle(code, given)


def test_the_catalogue_is_in_form_order():
    assert [c.code for c in CHANNELS] == [
        "website",
        "github",
        "discord",
        "mastodon",
        "bluesky",
        "linkedin",
        "instagram",
        "x",
    ]


@pytest.fixture
def ada(db):
    return User.objects.create_user("ada", email="ada@example.com")


@pytest.fixture
def rows(ada, conference):
    """A volunteer profile and a presenter of Ada's, typed in separately."""
    profile = VolunteerProfile.objects.create(
        user=ada,
        conference=conference,
        discord_username="ada_vol",
        github_username="ada-gh",
        x_username="ada_x",
    )
    presenter = Presenter.objects.create(
        conference=conference,
        user=ada,
        display_name="Ada",
        email="ada@example.com",
        github_username="ada-old",
        website_url="https://ada.example.org",
    )
    return profile, presenter


@pytest.mark.django_db
class TestTheRecord:
    def test_a_person_with_no_record_reads_as_their_rows_say(self, ada, rows):
        assert handles_of(ada) == {
            "discord": "ada_vol",
            "github": "ada-gh",  # the volunteer side first
            "x": "ada_x",
            "website": "https://ada.example.org",
        }
        assert handles_of(ada.pk) == handles_of(ada)
        assert handles_from_roles(User.objects.create_user("new").pk) == {}

    def test_saving_writes_the_record_and_every_row(self, ada, rows):
        profile, presenter = rows
        save_handles(ada, {"github": "ada-new", "mastodon": "@ada@fosstodon.org"})
        assert handles_of(ada) == {
            "github": "ada-new",
            "mastodon": "@ada@fosstodon.org",
        }
        profile.refresh_from_db()
        presenter.refresh_from_db()
        # The record rules the rows: a channel it lacks is blank on them.
        assert profile.github_username == presenter.github_username == "ada-new"
        assert profile.mastodon_url == presenter.mastodon_url == "@ada@fosstodon.org"
        assert profile.discord_username == "" and profile.x_username == ""
        assert presenter.website_url == ""
        # A blank removes the channel; an unnamed one is left alone.
        save_handles(ada, {"mastodon": ""})
        assert handles_of(ada) == {"github": "ada-new"}
        assert Handle.objects.filter(user=ada).count() == 1

    def test_pushing_with_no_record_changes_nothing(self, ada, rows):
        profile, presenter = rows
        push_handles(ada)
        profile.refresh_from_db()
        assert profile.discord_username == "ada_vol"

    def test_pushing_saves_only_presenters_that_changed(
        self, ada, rows, django_assert_num_queries
    ):
        save_handles(ada, {"github": "ada-same"})
        # A second push: the record, the account's pronouns, the volunteer
        # update, the presenter read; no presenter save.
        with django_assert_num_queries(4):
            push_handles(ada)

    def test_adopting_fills_the_blanks_then_rules(self, ada, rows):
        profile, presenter = rows
        Handle.objects.create(user=ada, channel="github", value="ada-mine")
        adopt_role_handles(ada)
        assert handles_of(ada) == {
            "github": "ada-mine",
            "discord": "ada_vol",
            "x": "ada_x",
            "website": "https://ada.example.org",
        }
        presenter.refresh_from_db()
        assert presenter.github_username == "ada-mine"
        assert presenter.discord_username == "ada_vol"

    def test_the_migration_fills_the_record_from_the_rows(self, ada, rows):
        migration.fill_from_roles(apps, None)
        assert dict(
            Handle.objects.filter(user=ada).values_list("channel", "value")
        ) == {
            "discord": "ada_vol",
            "github": "ada-gh",
            "x": "ada_x",
            "website": "https://ada.example.org",
        }


@pytest.mark.django_db
class TestTheAccountForm:
    def test_the_profile_page_edits_the_handles(self, client, ada, rows):
        profile, presenter = rows
        account = PortalProfile.objects.create(user=ada)
        client.force_login(ada)
        url = reverse("portal_account:portal_profile_edit", args=[account.pk])
        page = client.get(url).content.decode()
        assert "Your handles" in page and 'value="ada_vol"' in page
        response = client.post(
            url,
            {
                "first_name": "Ada",
                "last_name": "L",
                "pronouns": "she/her",
                "github": "ada-acct",
                "discord": "ada_vol",
                "linkedin": "linkedin.com/in/ada",
                "mastodon": "nope",
            },
        )
        assert "Mastodon" in response.content.decode()
        response = client.post(
            url,
            {
                "first_name": "Ada",
                "last_name": "L",
                "pronouns": "she/her",
                "github": "ada-acct",
                "discord": "ada_vol",
                "linkedin": "linkedin.com/in/ada",
            },
        )
        assert response.status_code == 302
        assert handles_of(ada) == {
            "github": "ada-acct",
            "discord": "ada_vol",
            "linkedin": "https://linkedin.com/in/ada",
        }
        profile.refresh_from_db()
        presenter.refresh_from_db()
        assert profile.github_username == presenter.github_username == "ada-acct"
        assert profile.linkedin_url == presenter.linkedin_url
        assert presenter.website_url == ""

    def test_the_form_lists_its_handle_fields(self, ada):
        form = PortalProfileForm(user=ada)
        assert [f.name for f in form.handle_fields()] == [c.code for c in CHANNELS]
        assert form.handle_values() == {c.code: "" for c in CHANNELS}

    def test_without_a_user_nothing_is_written(self, db):
        form = PortalProfileForm()
        form.init_handles(None)
        form.write_handles()
        assert Handle.objects.count() == 0


@pytest.mark.django_db
def test_the_admin_lists_handles(client, admin_user, ada):
    Handle.objects.create(user=ada, channel="github", value="ada-gh")
    client.force_login(admin_user)
    response = client.get(reverse("admin:portal_account_handle_changelist"))
    assert response.status_code == 200 and "ada-gh" in response.content.decode()
    assert str(Handle.objects.get()) == "ada: GitHub username ada-gh"


@pytest.mark.django_db
class TestPronouns:
    def test_the_account_is_the_record_and_the_rows_copy_it(self, ada, rows):
        profile, presenter = rows
        presenter.pronouns = "she/her"
        presenter.save()
        # No account yet: the newest presenter row speaks.
        assert pronouns_of(ada) == "she/her"
        assert pronouns_of(None) == ""
        account = PortalProfile.objects.create(user=ada)
        # A blank account is still the record: adopting fills it first.
        adopt_role_handles(ada)
        account.refresh_from_db()
        assert account.pronouns == "she/her"
        save_pronouns(ada, " they/them ")
        account.refresh_from_db()
        presenter.refresh_from_db()
        assert account.pronouns == presenter.pronouns == "they/them"
        # A push with no handle rows still carries the pronouns.
        Handle.objects.filter(user=ada).delete()
        account.pronouns = "xe/xem"
        account.save()
        push_handles(ada)
        presenter.refresh_from_db()
        assert presenter.pronouns == "xe/xem"

    def test_the_migration_fills_a_blank_account(self, ada, rows):
        profile, presenter = rows
        presenter.pronouns = "she/her"
        presenter.save()
        account = PortalProfile.objects.create(user=ada, pronouns="")
        other = User.objects.create_user("bo", email="bo@example.com")
        PortalProfile.objects.create(user=other, pronouns="he/him")
        migration.fill_from_roles(apps, None)
        account.refresh_from_db()
        assert account.pronouns == "she/her"
        assert PortalProfile.objects.get(user=other).pronouns == "he/him"

    def test_the_account_page_pushes_pronouns(self, client, ada, rows):
        profile, presenter = rows
        account = PortalProfile.objects.create(user=ada)
        client.force_login(ada)
        url = reverse("portal_account:portal_profile_edit", args=[account.pk])
        response = client.post(
            url, {"first_name": "Ada", "last_name": "L", "pronouns": "she/her"}
        )
        assert response.status_code == 302
        presenter.refresh_from_db()
        assert presenter.pronouns == "she/her"
