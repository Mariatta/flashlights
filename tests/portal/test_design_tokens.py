"""The design system's tokens and fonts ship with the portal (decision 0010):
one entry stylesheet, every font file present, nothing fetched from a
third party on page load."""

import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

TOKENS = Path(finders.find("css/tokens"))
STYLESHEETS = [Path(finders.find("css/flashlights.css"))] + sorted(TOKENS.glob("*.css"))


def test_entry_imports_every_token_file():
    entry = (TOKENS.parent / "flashlights.css").read_text()
    for name in (
        "fonts",
        "lucide",
        "colors",
        "typography",
        "spacing",
        "effects",
        "base",
    ):
        assert f'@import "./tokens/{name}.css";' in entry


def test_no_third_party_request_in_the_stylesheets():
    for sheet in STYLESHEETS:
        text = sheet.read_text()
        assert (
            "googleapis" not in text and "unpkg" not in text and "https://" not in text
        ), sheet


@pytest.mark.parametrize("sheet", ["tokens/fonts.css", "tokens/lucide.css"])
def test_every_font_url_resolves_to_a_shipped_file(sheet):
    text = (TOKENS.parent / sheet).read_text()
    urls = re.findall(r"url\(([^)]+)\)", text)
    assert urls
    for url in urls:
        relative = url.strip("\"'").replace("../../", "")
        assert finders.find(relative), f"{sheet}: {url} is not a static file"


def test_the_three_families_and_their_licences_ship():
    fonts = Path(finders.find("fonts"))
    names = {p.name for p in fonts.iterdir()}
    for family in (
        "bricolage-grotesque",
        "atkinson-hyperlegible-next",
        "atkinson-hyperlegible-mono",
    ):
        assert any(n.startswith(family) and n.endswith(".woff2") for n in names), family
        assert f"LICENSE-{family}.txt" in names
    assert {"lucide.woff2", "lucide.ttf", "LICENSE-lucide.txt"} <= names


@pytest.mark.django_db
def test_every_page_loads_the_entry_stylesheet_and_nothing_remote(client, conference):
    content = client.get(reverse("portal_stats")).content.decode()
    assert "css/flashlights" in content
    assert "fonts.googleapis.com" not in content and "unpkg.com" not in content


def test_bootstrap_is_mapped_onto_the_tokens():
    """portal.css re-themes Bootstrap through its variables (decision 0010):
    body type and surface, radii, the focus ring, the status colours; the
    old white logo chip for a navy navbar is gone."""
    css = Path(finders.find("css/portal.css")).read_text()
    for mapping in (
        "--bs-body-font-family: var(--font-body);",
        "--bs-body-bg: var(--surface-page);",
        "--bs-border-radius: var(--radius-md);",
        "--bs-border-radius-lg: var(--radius-lg);",
        "--bs-focus-ring-color: var(--focus-halo);",
        "--bs-success: var(--status-ok);",
        "--bs-danger: var(--status-stop);",
        "--bs-warning: var(--status-warn);",
        "--bs-card-border-radius: var(--radius-lg);",
        "min-height: var(--control-h-md);",
    ):
        assert mapping in css, mapping
    assert ".navbar-logo {\n    background: #fff;" not in css


def test_no_font_awesome_remains():
    """Icons are Lucide (icon-<name>); the Font Awesome kit and its classes
    are gone from templates, Python and scripts."""
    root = Path(finders.find("css")).parent.parent.parent
    folders = (
        "templates",
        "portal",
        "speakers",
        "volunteer",
        "sponsorship",
        "attendee",
        "common",
        "affiliations",
    )
    for folder in folders:
        for path in (root / folder).rglob("*"):
            if (
                path.suffix in (".html", ".py", ".js", ".md")
                and "migrations" not in path.parts
            ):
                text = path.read_text()
                assert not re.search(r"\bfa-[a-z0-9]", text), path
                assert "fontawesome" not in text, path


@pytest.mark.django_db
def test_pages_use_lucide_classes_only(client, conference):
    content = client.get("/").content.decode()
    assert "kit.fontawesome.com" not in content
    assert "fa-solid" not in content
