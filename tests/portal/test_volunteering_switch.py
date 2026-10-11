"""``VOLUNTEERING_ENABLED``: an instance that does not run volunteering."""

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import reverse

from portal_account.models import PortalProfile


@pytest.mark.django_db
class TestVolunteeringOff:
    def test_volunteer_pages_answer_404(self, client, portal_user, conference):
        client.force_login(portal_user)
        with override_settings(VOLUNTEERING_ENABLED=False):
            assert client.get(reverse("volunteer:index")).status_code == 404
        assert client.get(reverse("volunteer:index")).status_code == 200

    def test_nav_has_no_volunteer_tab(self, client, portal_user, conference):
        client.force_login(portal_user)
        with override_settings(VOLUNTEERING_ENABLED=False):
            content = client.get(reverse("portal_stats")).content.decode()
        assert reverse("volunteer:index") not in content

    def test_landing_has_no_volunteering_section(self, client, conference):
        with override_settings(VOLUNTEERING_ENABLED=False):
            content = client.get(reverse("index")).content.decode()
        assert "Sign up to volunteer" not in content
        assert settings.BRAND.title in content
        content = client.get(reverse("index")).content.decode()
        assert "Sign up to volunteer" in content

    def test_signed_in_member_lands_on_the_public_page(
        self, client, portal_user, conference
    ):
        # With no hub to send them to, the index renders rather than redirects,
        # and without the sign-in buttons.
        PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        with override_settings(VOLUNTEERING_ENABLED=False):
            response = client.get(reverse("index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Create an account" not in content
        assert reverse("volunteer:index") not in content

    def test_organizer_pages_hide_volunteer_entries(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        with override_settings(VOLUNTEERING_ENABLED=False):
            content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Review volunteers" not in content
        assert "Manage teams" not in content
        assert reverse("volunteer:volunteers_list") not in content
        assert reverse("teams") not in content


@pytest.mark.django_db
class TestApplicationsClosedForTheEdition:
    """The edition's "taking volunteer applications" flag: off, the public
    page says nothing about volunteering and sign-up refuses, while the
    team keeps its hub."""

    def test_landing_says_nothing_about_volunteering(self, client, conference):
        conference.volunteer_application_open = False
        conference.save()
        content = client.get(reverse("index")).content.decode()
        assert "Sign up to volunteer" not in content
        assert "Create an account" in content and "Sign in" in content
        # With every way in closed there is no empty band under the hero.
        assert "landing-sections" not in content
        conference.sponsors_url = "https://2025.example.org/sponsors/"
        conference.save()
        assert "landing-sections" in client.get(reverse("index")).content.decode()

    def test_landing_advertises_while_open(self, client, conference):
        content = client.get(reverse("index")).content.decode()
        assert "Sign up to volunteer" in content

    def test_hub_stays_but_sign_up_is_closed(self, client, portal_user, conference):
        conference.volunteer_application_open = False
        conference.save()
        client.force_login(portal_user)
        hub = client.get(reverse("volunteer:index"))
        assert hub.status_code == 200
        content = hub.content.decode()
        assert "not taking new volunteer applications" in content
        assert reverse("volunteer:volunteer_profile_new") not in content
        response = client.get(reverse("volunteer:volunteer_profile_new"), follow=True)
        assert response.redirect_chain[-1][0] == reverse("volunteer:index")
        content = response.content.decode()
        assert "not taking new volunteer applications" in content
        # Messages reach every page as Night toasts (Toast spec).
        assert 'id="portal-toasts"' in content and "portal-toast-info" in content

    def test_edition_form_carries_the_flag(self, client, admin_user, conference):
        client.force_login(admin_user)
        content = client.get(
            reverse("conference_edit", kwargs={"pk": conference.pk})
        ).content.decode()
        assert "Taking volunteer applications" in content
