"""Styles live in the stylesheets, not in templates: a ``<style>`` block in
a page escapes the design tokens and is missed when the look changes."""

import pathlib

from tests.portal.test_template_comments import REPO_ROOT, template_files

#: Upstream's Select2 overrides with fixed colours; moving them means
#: restyling the field on design tokens, which is its own change.
KNOWN = {pathlib.Path("templates/volunteer/volunteerprofile_form.html")}


def test_no_template_carries_a_style_block():
    found = [
        path.relative_to(REPO_ROOT)
        for path in template_files()
        if "<style" in path.read_text()
    ]
    assert set(found) == KNOWN
