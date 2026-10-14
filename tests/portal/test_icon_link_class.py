"""No link carries Bootstrap's ``icon-link`` class.

The Lucide icon font styles every class starting with ``icon-``, so
``icon-link`` on a link sets its text in the icon font and puts a chain
glyph in front of it. ``<i class="icon-link">`` is the Lucide link icon and
is fine; for a link with a trailing icon use
``d-inline-flex align-items-center gap-1``.
"""

import re

import pytest

from tests.portal.test_template_comments import REPO_ROOT, template_files

LINK_WITH_ICON_LINK = re.compile(
    r'<a\b[^>]*\bclass="[^"]*(?<![\w-])icon-link(?![\w-])', re.DOTALL
)


def test_the_pattern_catches_a_link():
    assert LINK_WITH_ICON_LINK.search('<a href="/" class="icon-link">')
    assert not LINK_WITH_ICON_LINK.search('<a href="/"><i class="icon-link"></i>')
    assert not LINK_WITH_ICON_LINK.search('<a href="/" class="icon-link-2">')


@pytest.mark.parametrize("path", list(template_files()), ids=str)
def test_no_link_uses_bootstrap_icon_link(path):
    assert not LINK_WITH_ICON_LINK.search(path.read_text()), (
        f"{path.relative_to(REPO_ROOT)} puts icon-link on a link, which the "
        "Lucide font turns into icon glyphs. Use "
        "d-inline-flex align-items-center gap-1 instead."
    )
