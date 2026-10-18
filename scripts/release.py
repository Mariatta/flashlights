#!/usr/bin/env python
"""Check a release tag and print its notes.

The version lives in ``pyproject.toml``; each release has a section in
``CHANGELOG.md`` headed ``## X.Y.Z (YYYY-MM-DD)``, written before the tag.
The release workflow runs

    python scripts/release.py vX.Y.Z

which fails unless the tag is ``v`` plus the pyproject version and the
changelog has a dated section for it, and prints that section, which
becomes the GitHub release's notes. docs/developer/releasing.md has the
steps.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## (\S+) \((.+)\)\s*$", re.MULTILINE)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ReleaseError(Exception):
    pass


def version(root=ROOT):
    """The version ``pyproject.toml`` declares."""
    with open(root / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def notes(changelog, release):
    """The body of ``release``'s section, which must carry a date."""
    headings = list(HEADING.finditer(changelog))
    for index, heading in enumerate(headings):
        if heading.group(1) != release:
            continue
        if not DATE.fullmatch(heading.group(2)):
            raise ReleaseError(
                f"CHANGELOG.md: {release} is ({heading.group(2)}); "
                "date it before tagging"
            )
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else None
        return changelog[start:end].strip()
    raise ReleaseError(f"CHANGELOG.md has no section for {release}")


def check(tag, root=ROOT):
    """The notes for ``tag``, once the tag, version and changelog agree."""
    declared = version(root)
    if tag != f"v{declared}":
        raise ReleaseError(f"tag {tag} does not match pyproject.toml's {declared}")
    return notes((root / "CHANGELOG.md").read_text(), declared)


def main(argv=None, root=ROOT):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python scripts/release.py vX.Y.Z", file=sys.stderr)
        return 2
    try:
        print(check(argv[0], root))
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
