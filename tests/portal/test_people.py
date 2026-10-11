"""People cells and status chips (PersonRow spec)."""

import pytest

from portal.people import initials, person_cell, status_chip


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Ana Souza", "AS"),
        ("ana", "A"),
        ("Ana de Souza Lima", "AD"),
        ("", "?"),
        (None, "?"),
    ],
)
def test_initials(name, expected):
    assert initials(name) == expected


def test_person_cell_links_and_escapes():
    html = person_cell(
        "Ana Souza", href="/people/1/", meta="Volunteer <b>·</b> Programs"
    )
    assert 'class="person-avatar" aria-hidden="true">AS<' in html
    assert '<a href="/people/1/">Ana Souza</a>' in html
    # Everything passed in is escaped, the meta line included.
    assert (
        '<div class="person-meta">Volunteer &lt;b&gt;·&lt;/b&gt; Programs</div>' in html
    )
    plain = person_cell("Ana Souza")
    assert "<a " not in plain and "person-meta" not in plain


def test_status_chip_tones():
    assert status_chip("Approved", "ok") == (
        '<span class="status-chip status-chip-ok">Approved</span>'
    )
    assert "status-chip-neutral" in status_chip("Cancelled")
    with pytest.raises(ValueError):
        status_chip("Odd", "purple")
