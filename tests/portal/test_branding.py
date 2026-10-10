"""The instance identity seam: environment in, theme, images and tags out."""

import io

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from common.markdown_emails import render_markdown_email
from portal import branding


class TestFromEnv:
    def test_defaults(self):
        brand = branding.from_env({})
        assert brand.title == "Flashlights"
        assert brand.short_name == "Flashlights"
        assert brand.description == "Flashlights: the organisers' portal"
        assert brand.preset == "beam"
        assert brand.primary == "#ffd43b"
        assert brand.primary_hover == "#ffe27a"
        assert brand.primary_active == "#f2bd00"
        # Beam cannot carry white text: Night on the button, Beam 700 as text.
        assert brand.text_on_accent == branding.NIGHT
        assert brand.accent_ink == "#7a5c00"
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
        assert brand.primary == "#b45309"
        assert brand.text_on_accent == branding.WHITE  # a dark accent
        assert brand.accent_ink == "#b45309"  # reads on Paper as it is
        assert brand.docs_url == "https://docs.test/"
        assert brand.terms_url == "https://x.test/terms/"

    def test_teal_keeps_its_shades_and_white_ink(self):
        brand = branding.from_env({"BRAND_PRESET": "teal"})
        assert (brand.primary, brand.primary_hover, brand.primary_active) == (
            "#0f766e",
            "#0d5f59",
            "#0b4f4a",
        )
        assert brand.text_on_accent == branding.WHITE

    def test_unknown_preset_is_refused_with_the_choices(self):
        with pytest.raises(ImproperlyConfigured) as excinfo:
            branding.from_env({"BRAND_PRESET": "neon"})
        assert "beam, copper, indigo, raspberry, teal" in str(excinfo.value)

    def test_dark_custom_accent_darkens_both_ways(self):
        brand = branding.from_env({"BRAND_PRIMARY": "#1D4ED8"})
        assert brand.primary == "#1d4ed8"
        assert brand.primary_hover == "#1a45be"
        assert brand.primary_active == "#173ead"
        assert brand.text_on_accent == branding.WHITE
        assert brand.accent_ink == "#1d4ed8"

    def test_light_custom_accent_lightens_on_hover_and_takes_night_ink(self):
        brand = branding.from_env({"BRAND_PRIMARY": "#ffff00"})
        assert brand.text_on_accent == branding.NIGHT
        assert brand.primary_hover == "#ffff4c"  # lighter
        assert brand.primary_active == "#e6e600"  # darker
        # Yellow text on Paper does not read; the ink is darkened until it does.
        assert brand.accent_ink != "#ffff00"
        paper = branding.parse_hex(branding.PAPER)
        assert branding.contrast(branding.parse_hex(brand.accent_ink), paper) >= 4.5

    @pytest.mark.parametrize("value", ["1d4ed8", "#1d4e", "#zzzzzz", "blue"])
    def test_malformed_primary_is_refused(self, value):
        with pytest.raises(ImproperlyConfigured, match="rrggbb"):
            branding.from_env({"BRAND_PRIMARY": value})

    @pytest.mark.parametrize("value", ["#000000", "#ffffff", "#808080", "#ff00ff"])
    def test_every_colour_gets_an_ink_that_reads(self, value):
        """Against Night or against white, one ink always clears 3:1, so no
        accent is refused; the mid-grey worst case clears it on both."""
        brand = branding.from_env({"BRAND_PRIMARY": value})
        rgb = branding.parse_hex(value)
        assert branding.contrast(rgb, branding.parse_hex(brand.text_on_accent)) >= 3


class TestBrand:
    def test_theme_css_carries_every_token(self):
        css = branding.from_env({"BRAND_PRESET": "indigo"}).theme_css()
        assert "--accent: #4f46e5;" in css
        assert "--accent-rgb: 79, 70, 229;" in css
        assert "--accent-hover: #4338ca;" in css
        assert "--accent-press: #3730a3;" in css
        assert "--accent-ink: #4f46e5;" in css
        assert "--text-on-accent: #ffffff;" in css
        assert "--focus-halo: var(--accent);" in css
        # The portal's older names and Bootstrap's build on the accent; the
        # ink (navbar, footer) is the fixed Night.
        assert "--brand-primary: var(--accent);" in css
        assert "--brand-ink: #0f0f0d;" in css
        assert "--bs-primary: var(--accent);" in css
        assert "--bs-link-color: var(--accent-ink);" in css

    def test_version_changes_with_the_colours_and_the_initial(self):
        beam = branding.from_env({})
        copper = branding.from_env({"BRAND_PRESET": "copper"})
        renamed = branding.from_env({"SITE_TITLE": "Summit"})
        assert len(beam.version) == 12
        assert beam.version != copper.version
        assert beam.version != renamed.version
        assert beam.version == branding.from_env({}).version

    def test_favicon_uses_the_initial_and_primary(self):
        brand = branding.from_env(
            {"SITE_SHORT_NAME": "summit", "BRAND_PRESET": "copper"}
        )
        svg = brand.favicon_svg()
        assert brand.initial == "S"
        assert 'fill="#b45309"' in svg
        assert 'fill="#ffffff">S</text>' in svg  # white on a dark accent
        beam = branding.from_env({"SITE_SHORT_NAME": "summit"}).favicon_svg()
        assert 'fill="#0f0f0d">S</text>' in beam  # Night on Beam

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
            content = client.get(reverse("portal_stats")).content.decode()
        assert '<meta property="og:site_name" content="Summit 2027" />' in content
        assert 'content="https://x.test/og.png"' in content
        assert '<link rel="icon" href="https://x.test/favicon.png" />' in content
        assert 'src="https://x.test/logo.svg"' in content
        assert 'href="https://docs.test/">Documentation</a>' in content
        assert reverse("brand_favicon") not in content

    def test_base_template_without_optional_assets(self, client, conference):
        with override_settings(BRAND=branding.from_env({})):
            content = client.get(reverse("portal_stats")).content.decode()
        # No share image of its own: the generated card stands in.
        assert reverse("brand_share_card") in content
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


@pytest.mark.django_db
class TestGeneratedImages:
    """The PNG favicon twins and the share card, drawn with Pillow."""

    def _png(self, client, name):
        response = client.get(reverse(name))
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert response["Cache-Control"].startswith("public, max-age=31536000")
        return Image.open(io.BytesIO(response.content))

    def test_favicon_png_sizes(self, client):
        assert self._png(client, "brand_favicon_png").size == (32, 32)
        assert self._png(client, "brand_apple_touch_icon").size == (180, 180)

    def test_favicon_png_is_the_primary_colour(self, client):
        image = self._png(client, "brand_favicon_png").convert("RGBA")
        # A corner is transparent (the rounded square), the centre-top is
        # the primary colour (above the initial).
        assert image.getpixel((0, 0))[3] == 0
        primary = branding.parse_hex(settings.BRAND.primary)
        assert image.getpixel((16, 4))[:3] == primary

    def test_share_card_is_open_graph_sized(self, client):
        image = self._png(client, "brand_share_card")
        assert image.size == (1200, 630)
        assert image.getpixel((10, 10)) == branding.parse_hex(settings.BRAND.primary)

    def test_long_titles_shrink_to_fit(self):
        brand = branding.from_env(
            {
                "SITE_TITLE": "A " + "very " * 30 + "long event name",
                "SITE_DESCRIPTION": "x",
            }
        )
        assert Image.open(io.BytesIO(brand.share_card_png())).size == (1200, 630)

    def test_version_follows_the_wording(self):
        one = branding.from_env({"SITE_TITLE": "Summit"})
        two = branding.from_env({"SITE_TITLE": "Summit", "SITE_DESCRIPTION": "Other"})
        assert one.version != two.version

    def test_base_template_links_the_generated_images(self, client, conference):
        with override_settings(BRAND=branding.from_env({})):
            content = client.get(reverse("portal_stats")).content.decode()
        assert f'{reverse("brand_favicon_png")}?v=' in content
        assert f'{reverse("brand_apple_touch_icon")}?v=' in content
        assert f'content="http://testserver{reverse("brand_share_card")}?v=' in content
        assert 'property="og:image:alt"' in content

    def test_base_template_prefers_the_instance_share_image(self, client, conference):
        brand = branding.from_env({"SITE_OG_IMAGE": "https://x.test/og.png"})
        with override_settings(BRAND=brand):
            content = client.get(reverse("portal_stats")).content.decode()
        assert 'content="https://x.test/og.png"' in content
        assert reverse("brand_share_card") not in content


@pytest.mark.django_db
class TestEmailWording:
    def test_greeting_and_sign_off_use_the_title(self, conference):
        markdown, _, text = render_markdown_email("emails/base_email.md", {})
        assert "Hello from Flashlights." in markdown
        assert "Thank you for using **Flashlights**." in markdown
        assert "!" not in text
