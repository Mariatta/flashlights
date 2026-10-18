"""Every page is served by the instance itself: the browser libraries are
vendored under portal/static/vendor/ from the versions package.json pins, and
no template or setting asks another server for a script, stylesheet, image
or frame."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

ROOT = Path(settings.BASE_DIR)
PINNED = json.loads((ROOT / "package.json").read_text())["devDependencies"]
VENDORED = json.loads((ROOT / "frontend" / "vendored.json").read_text())
VENDOR = Path(finders.find("vendor"))

# A tag that makes the browser fetch: <script src>, <link href>, <img src>,
# <iframe src>, <source src>, <video src> or <audio src> at an absolute URL.
REMOTE = re.compile(
    r"<(?:script|link|img|iframe|source|video|audio)\b[^>]*?\b(?:src|href)=[\"']"
    r"(?:https?:)?//",
    re.IGNORECASE,
)
TEMPLATES = sorted(
    path
    for folder in [ROOT / "templates", *ROOT.glob("*/templates")]
    for path in folder.rglob("*.html")
)


@pytest.mark.parametrize("name", sorted(VENDORED))
def test_vendored_version_is_the_pinned_one(name):
    """A version bump in package.json (a Dependabot pull request, say) fails
    here until npm run vendor copies the new files."""
    assert VENDORED[name]["version"] == PINNED[name], (
        f"{name}: package.json pins {PINNED[name]}, the vendored copy is "
        f"{VENDORED[name]['version']}; run npm ci && npm run vendor"
    )


@pytest.mark.parametrize("name", sorted(VENDORED))
def test_vendored_files_are_the_recorded_ones(name):
    for path, digest in VENDORED[name]["files"].items():
        found = finders.find(path)
        assert found, f"{path} is missing; run npm run vendor"
        assert hashlib.sha256(Path(found).read_bytes()).hexdigest() == digest, (
            f"{path} differs from the {name} {PINNED[name]} release; "
            "vendored files are never edited by hand"
        )


def test_every_vendored_file_is_recorded():
    recorded = {path for entry in VENDORED.values() for path in entry["files"]}
    shipped = {
        f"vendor/{path.relative_to(VENDOR).as_posix()}"
        for path in VENDOR.rglob("*")
        if path.is_file()
    }
    assert shipped == recorded


def test_every_vendored_library_ships_its_licence():
    for name, entry in VENDORED.items():
        assert any("LICENSE" in path for path in entry["files"]), name


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_template_loads_from_another_server(template):
    match = REMOTE.search(template.read_text())
    assert not match, f"{match.group(0)}...: vendor it under portal/static/"


def test_bootstrap_settings_point_at_the_vendored_copy():
    for key in ("css_url", "javascript_url"):
        assert settings.BOOTSTRAP5[key]["url"].startswith("/static/vendor/"), key


@pytest.mark.django_db
def test_stats_page_draws_with_the_vendored_chart_library(client, conference):
    content = client.get(reverse("portal_stats")).content.decode()
    # {% static %} may add a content hash before the extension.
    assert "vendor/chartjs/chart.umd.min." in content
    assert "vendor/bootstrap/bootstrap.min." in content
    assert not REMOTE.search(content)
