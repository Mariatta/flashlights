"""The instance identity seam: environment in, theme and tags out."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse

from portal import branding


class TestFromEnv:
    def test_defaults(self):
        brand = branding.from_env({})
        assert brand.title == "Flashlights"
        assert brand.short_name == "Flashlights"
        assert brand.description == "Flashlights: the organisers' portal"
        assert brand.preset == "teal"
        assert brand.primary == "#0f766e"
        assert brand.primary_hover == "#0d5f59"
        assert brand.primary_active == "#0b4f4a"
        assert brand.ink == "#142a36"
        assert brand.logo == brand.favicon == brand.og_image == ""
        assert brand.docs_url == brand.terms_url == ""

    def test_every_key(self):
        brand = branding.from_env(
            {
                "SITE_TITLE": " PyCon Maintainer Summit ",
                "SITE_SHORT_NAME": "Summit",
                "SITE_DESCRIPTION": "Organisers only.",
                "SITE_LOGO": "https://x.test/logo.svg",
                "SITE_FAVICON": "https://x.test/favicon.png",
                "SITE_OG_IMAGE": "https://x.test/og.png",
                "BRAND_PRESET": "copper",
                "DOCS_URL": "https://docs.test/",
                "TERMS_URL": "https://x.test/terms/",
            }
        )
        assert brand.title == "PyCon Maintainer Summit"
        assert brand.short_name == "Summit"
        assert brand.description == "Organisers only."
        assert brand.logo == "https://x.test/logo.svg"
        assert brand.favicon == "https://x.test/favicon.png"
        assert brand.og_image == "https://x.test/og.png"
        assert (brand.primary, brand.ink) == ("#b45309", "#142a36")
        assert brand.docs_url == "https://docs.test/"
        assert brand.terms_url == "https://x.test/terms/"

    def test_raspberry_keeps_the_navy_ink(self):
        brand = branding.from_env({"BRAND_PRESET": "raspberry"})
        assert (brand.primary, brand.primary_hover, brand.primary_active) == (
            "#ee264d",
            "#d11f42",
            "#c01f3f",
        )
        assert brand.ink == "#152035"

    def test_unknown_preset_is_refused_with_the_choices(self):
        with pytest.raises(ImproperlyConfigured) as excinfo:
            branding.from_env({"BRAND_PRESET": "neon"})
        assert "copper, indigo, raspberry, teal" in str(excinfo.value)

    def test_custom_primary_derives_the_shades(self):
        brand = branding.from_env({"BRAND_PRIMARY": "#1D4ED8"})
        assert brand.preset == "teal"  # the preset still supplies the ink
        assert brand.primary == "#1d4ed8"
        assert brand.primary_hover == "#1a45be"
        assert brand.primary_active == "#173ead"

    @pytest.mark.parametrize("value", ["1d4ed8", "#1d4e", "#zzzzzz", "blue"])
    def test_malformed_primary_is_refused(self, value):
        with pytest.raises(ImproperlyConfigured, match="rrggbb"):
            branding.from_env({"BRAND_PRIMARY": value})

    def test_pale_primary_is_refused_for_contrast(self):
        with pytest.raises(ImproperlyConfigured) as excinfo:
            branding.from_env({"BRAND_PRIMARY": "#ffff00"})
        message = str(excinfo.value)
        assert "1.1:1 contrast" in message
        assert "at least 3:1" in message


class TestBrand:
    def test_theme_css_carries_every_token(self):
        css = branding.from_env({"BRAND_PRESET": "indigo"}).theme_css()
        assert "--brand-primary: #4f46e5;" in css
        assert "--brand-primary-rgb: 79, 70, 229;" in css
        assert "--brand-primary-hover: #4338ca;" in css
        assert "--brand-primary-active: #3730a3;" in css
        assert "--brand-ink: #142a36;" in css
        assert "--bs-primary: var(--brand-primary);" in css
        assert "--bs-link-hover-color-rgb: var(--brand-primary-hover-rgb);" in css

    def test_version_changes_with_the_colours_and_the_initial(self):
        teal = branding.from_env({})
        copper = branding.from_env({"BRAND_PRESET": "copper"})
        renamed = branding.from_env({"SITE_TITLE": "Summit"})
        assert len(teal.version) == 12
        assert teal.version != copper.version
        assert teal.version != renamed.version
        assert teal.version == branding.from_env({}).version

    def test_favicon_uses_the_initial_and_primary(self):
        brand = branding.from_env(
            {"SITE_SHORT_NAME": "summit", "BRAND_PRESET": "copper"}
        )
        svg = brand.favicon_svg()
        assert brand.initial == "S"
        assert 'fill="#b45309"' in svg
        assert ">S</text>" in svg

    def test_blank_initial_falls_back(self):
        brand = branding.from_env({"SITE_SHORT_NAME": "  "})
        assert brand.initial == "F"  # short name fell back to the title


@pytest.mark.django_db
class TestViews:
    def test_theme_css_is_the_brand_stylesheet_cached_for_a_year(self, client):
        response = client.get(reverse("brand_theme_css"))
        assert response.status_code == 200
        assert response["Content-Type"] == "text/css"
        assert response["Cache-Control"] == "public, max-age=31536000, immutable"
        assert "--brand-primary:" in response.content.decode()

    def test_favicon_is_svg(self, client):
        response = client.get(reverse("brand_favicon"))
        assert response.status_code == 200
        assert response["Content-Type"] == "image/svg+xml"
        assert response.content.startswith(b"<svg")

    def test_base_template_reads_the_brand(self, client, conference):
        brand = branding.from_env(
            {
                "SITE_TITLE": "Summit 2027",
                "SITE_SHORT_NAME": "Summit",
                "SITE_LOGO": "https://x.test/logo.svg",
                "SITE_FAVICON": "https://x.test/favicon.png",
                "SITE_OG_IMAGE": "https://x.test/og.png",
                "DOCS_URL": "https://docs.test/",
            }
        )
        with override_settings(BRAND=brand):
            content = client.get(reverse("chapters")).content.decode()
        assert '<meta property="og:site_name" content="Summit 2027" />' in content
        assert 'content="https://x.test/og.png"' in content
        assert '<link rel="icon" href="https://x.test/favicon.png" />' in content
        assert 'src="https://x.test/logo.svg"' in content
        assert 'href="https://docs.test/">Documentation</a>' in content
        assert reverse("brand_favicon") not in content

    def test_base_template_without_optional_assets(self, client, conference):
        with override_settings(BRAND=branding.from_env({})):
            content = client.get(reverse("chapters")).content.decode()
        assert "og:image" not in content
        assert "navbar-logo" not in content
        assert "Documentation" not in content
        assert reverse("brand_favicon") in content


@pytest.mark.django_db
class TestPolicyLinks:
    def test_agreements_page_links_only_what_is_configured(
        self, client, conference, django_user_model
    ):
        user = django_user_model.objects.create_user("ada", "ada@example.com", "pw")
        client.force_login(user)
        url = reverse("portal_account:agreements")
        conference.coc_url = ""
        conference.save()
        with override_settings(BRAND=branding.from_env({})):
            content = client.get(url).content.decode()
        assert "Read the Code of Conduct" not in content
        assert "Read the Terms of Service" not in content
        conference.coc_url = "https://x.test/coc/"
        conference.save()
        with override_settings(
            BRAND=branding.from_env({"TERMS_URL": "https://x.test/terms/"})
        ):
            content = client.get(url).content.decode()
        assert 'href="https://x.test/coc/"' in content
        assert 'href="https://x.test/terms/"' in content

    def test_signup_terms_label_with_and_without_a_link(self, client, conference):
        url = reverse("account_signup")
        with override_settings(BRAND=branding.from_env({})):
            content = client.get(url).content.decode()
        assert "I agree to the Terms of Service" in content
        assert "pyladiescon-portal-docs" not in content
        with override_settings(
            BRAND=branding.from_env({"TERMS_URL": "https://x.test/terms/"})
        ):
            content = client.get(url).content.decode()
        assert 'href="https://x.test/terms/"' in content
