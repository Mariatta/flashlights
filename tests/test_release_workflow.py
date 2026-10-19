"""The release workflow publishes this version's docs next to the image."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.mkdocs_hooks import on_config, on_files

ROOT = Path(__file__).resolve().parent.parent


def test_the_docs_job_follows_the_release_and_publishes_the_tag_and_latest():
    jobs = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())["jobs"]
    docs = jobs["docs"]
    assert docs["needs"] == "release"
    assert docs["permissions"] == {"contents": "write"}
    checkout = next(
        s for s in docs["steps"] if s.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0  # mike reads the gh-pages history
    run = "\n".join(step.get("run", "") for step in docs["steps"])
    assert 'mike deploy --push --update-aliases "${GITHUB_REF_NAME#v}" latest' in run
    assert "mike set-default --push latest" in run


def test_mike_is_a_docs_dependency_and_the_site_offers_the_version_selector():
    requirements = (ROOT / "requirements-docs.txt").read_text().split()
    assert any(line.startswith("mike==") for line in requirements)
    config = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)
    assert config["extra"]["version"] == {"provider": "mike"}


def test_the_hook_puts_the_slash_back_on_a_versioned_site_url():
    """mike sets site_url to the version's folder without a trailing
    slash, and the RSS plugin joins image paths to it as text."""
    config = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)
    assert config["hooks"] == ["scripts/mkdocs_hooks.py"]
    versioned = SimpleNamespace(site_url="https://docs.test/flashlights/0.1.0")
    assert on_config(versioned).site_url == "https://docs.test/flashlights/0.1.0/"
    for untouched in ("https://docs.test/flashlights/", "", None):
        assert on_config(SimpleNamespace(site_url=untouched)).site_url == untouched


def test_the_hook_hands_the_slashed_site_url_to_the_rss_plugin():
    """The RSS plugin keeps its own copy of site_url from before the hook
    ran; the copy follows at the next event, and a site without the
    plugin, or without a site_url, is left alone."""
    cards = SimpleNamespace(mkdocs_site_url="https://docs.test/flashlights/0.1.0")
    rss = SimpleNamespace(integration_material_social_cards=cards)
    config = SimpleNamespace(
        site_url="https://docs.test/flashlights/0.1.0/", plugins={"rss": rss}
    )
    assert on_files(["a file"], config) == ["a file"]
    assert cards.mkdocs_site_url == "https://docs.test/flashlights/0.1.0/"
    on_files([], SimpleNamespace(site_url="https://docs.test/", plugins={}))
    cards.mkdocs_site_url = "kept"
    on_files([], SimpleNamespace(site_url=None, plugins={"rss": rss}))
    assert cards.mkdocs_site_url == "kept"
