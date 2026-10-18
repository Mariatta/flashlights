"""The release helper: a tag must match the pyproject version, and the
changelog must have a dated section for it before the image is published."""

import pytest

from scripts import release

CHANGELOG = """# Changelog

## 0.2.0 (unreleased)

- Next.

## 0.1.1 (2026-11-02)

- A fix.

## 0.1.0 (2026-11-01)

- First.
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.1"\n')
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    return tmp_path


def test_the_current_version_has_a_changelog_section():
    """Bumping the version means writing its entry, dated or not yet."""
    changelog = (release.ROOT / "CHANGELOG.md").read_text()
    assert f"## {release.version()} (" in changelog


def test_notes_are_the_section_body():
    assert release.notes(CHANGELOG, "0.1.1") == "- A fix."
    assert release.notes(CHANGELOG, "0.1.0") == "- First."


def test_an_undated_section_cannot_be_released():
    with pytest.raises(release.ReleaseError, match="date it before tagging"):
        release.notes(CHANGELOG, "0.2.0")


def test_a_missing_section_cannot_be_released():
    with pytest.raises(release.ReleaseError, match="no section for 0.3.0"):
        release.notes(CHANGELOG, "0.3.0")


def test_check_needs_the_tag_to_match_the_version(root):
    assert release.check("v0.1.1", root) == "- A fix."
    with pytest.raises(release.ReleaseError, match="does not match"):
        release.check("v0.1.0", root)
    with pytest.raises(release.ReleaseError, match="does not match"):
        release.check("0.1.1", root)


def test_main_prints_the_notes_or_the_reason(root, capsys):
    assert release.main(["v0.1.1"], root) == 0
    assert capsys.readouterr().out == "- A fix.\n"
    assert release.main(["v9.9.9"], root) == 1
    assert "release: tag v9.9.9" in capsys.readouterr().err
    assert release.main([], root) == 2
    assert "usage" in capsys.readouterr().err
