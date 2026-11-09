"""The design system's tokens and fonts ship with the portal:
one entry stylesheet, every font file present, nothing fetched from a
third party on page load."""

import functools
import hashlib
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from portal import branding
from speakers.constants import SessionStatus
from speakers.tables import STATUS_BADGE_CLASSES

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
    """portal.css re-themes Bootstrap through its variables:
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
        # The rail, breadcrumbs and tabs (SideRail, Breadcrumbs, Tabs specs).
        "--bs-nav-pills-link-active-bg: var(--night-950);",
        '--bs-breadcrumb-divider: "\\203A";',
        "border-bottom: 3px solid transparent;",
        # Forms (Input, Select, Checkbox, Switch specs).
        '.invalid-feedback::before {\n    font-family: "lucide";',
        ".form-switch .form-check-input:checked {",
        '.form-check-input:checked[type="checkbox"] {',
    ):
        assert mapping in css, mapping
    assert ".navbar-logo {\n    background: #fff;" not in css


TONES = [
    "primary",
    "secondary",
    "success",
    "danger",
    "warning",
    "info",
    "light",
    "dark",
]
DECLARATION = re.compile(r"(?<![\w-])([\w-]+)\s*:\s*([^;]+)")
REFERENCE = re.compile(r"var\((--[\w-]+)(?:,([^()]*))?\)")


def _rules(css):
    """(selector, property, value, important) for each declaration of each
    top-level rule, in source order. At-rules (media queries, keyframes,
    font faces) are left out: none of them styles a light-mode page."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found, depth, start = [], 0, 0
    for index, char in enumerate(css):
        if char == "{":
            if depth == 0:
                prelude, body_start = css[start:index].strip(), index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                if not prelude.startswith("@"):
                    for name, value in DECLARATION.findall(css[body_start:index]):
                        important = "!important" in value
                        value = value.replace("!important", "").strip()
                        for selector in prelude.split(","):
                            found.append((selector.strip(), name, value, important))
                start = index + 1
        elif char == ";" and depth == 0:
            start = index + 1
    return tuple(found)


@functools.cache
def _stylesheet(path):
    return _rules(Path(path).read_text())


@functools.cache
def _page_rules(preset):
    """Every rule a page carries, in the order base.html links the
    stylesheets: Bootstrap, the tokens, the instance theme, portal.css."""
    entry = (TOKENS.parent / "flashlights.css").read_text()
    tokens = re.findall(r'@import "\./tokens/([\w-]+)\.css";', entry)
    theme = branding.from_env({"BRAND_PRESET": preset}).theme_css()
    return (
        _stylesheet(finders.find("vendor/bootstrap/bootstrap.min.css"))
        + sum((_stylesheet(TOKENS / f"{name}.css") for name in tokens), ())
        + _rules(theme)
        + _stylesheet(finders.find("css/portal.css"))
    )


def _computed(preset, classes):
    """The properties an element with ``classes`` ends up with, and the
    selector each one came from. Of the rules made only of classes the
    element has, the highest (!important, specificity, source order) wins,
    as in the cascade; custom properties not set on the element come from
    :root."""
    classes = set(classes.split())
    values, origins, ranks = {}, {}, {}
    for order, (selector, name, value, important) in enumerate(_page_rules(preset)):
        if selector == ":root":
            if name not in ranks:
                values[name] = value
            continue
        if not re.fullmatch(r"(\.[\w-]+)+", selector):
            continue
        names = selector[1:].split(".")
        rank = (important, len(names), order)
        if set(names) <= classes and rank > ranks.get(name, (False, 0, -1)):
            values[name], origins[name], ranks[name] = value, selector, rank
    return values, origins


def _resolve(value, values, seen=()):
    """``value`` with its var() references followed, fallbacks included. A
    reference to nothing, or a property that refers to itself, fails the
    test that met it rather than crashing or looping."""

    def follow(match):
        name, fallback = match[1], match[2]
        if name in seen:
            pytest.fail(f"{name} refers to itself: {' -> '.join(seen)}")
        if name in values:
            return _resolve(values[name], values, seen + (name,))
        if fallback is None:
            pytest.fail(f"{name} is not defined")
        return fallback.strip()

    while REFERENCE.search(value):
        value = REFERENCE.sub(follow, value)
    return value


def test_a_broken_reference_fails_one_case_only():
    """A renamed token or a property that refers to itself fails the case
    that meets it, with its name, instead of crashing or looping."""
    with pytest.raises(pytest.fail.Exception, match="--gone is not defined"):
        _resolve("var(--gone)", {})
    with pytest.raises(pytest.fail.Exception, match="--loop refers to itself"):
        _resolve("var(--loop)", {"--loop": "var(--loop)"})
    assert _resolve("var(--gone, #fff)", {}) == "#fff"


def _colour(value):
    """(rgb, alpha) for a hex colour or an rgb()/RGBA() one."""
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return branding.parse_hex("#" + digits), 1.0
    numbers = re.findall(r"[\d.]+", value)
    alpha = float(numbers[3]) if len(numbers) > 3 else 1.0
    return tuple(int(float(c)) for c in numbers[:3]), alpha


def _paint(preset, classes):
    """The text and background colours an element with ``classes`` shows."""
    values, origins = _computed(preset, classes)
    text = _colour(_resolve(values["color"], values))
    background = _colour(_resolve(values["background-color"], values))
    return text, background, origins


@pytest.mark.parametrize("preset", sorted(branding.PRESETS))
@pytest.mark.parametrize("tone", TONES)
@pytest.mark.parametrize(
    "element",
    [
        "badge text-bg-{}",
        "badge bg-{}",
        "card text-bg-{}",
        "list-group-item text-bg-{}",
    ],
)
def test_every_tone_reads(preset, tone, element):
    """The tokens change Bootstrap's backgrounds but not the text colour it
    picked for them (black on info, warning and light, white on the rest),
    so "Confirmed" read black on dark grey. Each tone clears WCAG AA on
    every accent preset: as text-bg-* on a badge, a card or a list item,
    and as a plain bg-* badge, which keeps the badge's own text colour."""
    text, background, origins = _paint(preset, element.format(tone))
    assert text[1] == background[1] == 1.0, origins
    assert branding.contrast(text[0], background[0]) >= 4.5, origins


@pytest.mark.parametrize("tone", ["primary", "success", "info", "warning"])
def test_a_text_utility_still_colours_a_plain_bg_badge(tone):
    """The portal sets a plain bg-* badge's text through the badge's own
    colour, so an explicit text-* utility on the same badge still wins."""
    _, _, origins = _paint("beam", f"badge bg-{tone} bg-opacity-10 text-body")
    assert origins["color"] == ".text-body"


@pytest.mark.parametrize("element", ["badge bg-success", "badge text-bg-success"])
def test_a_green_badge_keeps_its_opacity_utilities(element):
    """The green badge's darker shade changes the tone, not the background,
    so bg-opacity-* still tints it."""
    _, background, _ = _paint("beam", f"{element} bg-opacity-25")
    assert background == (branding.parse_hex("#145c34"), 0.25)


@pytest.mark.parametrize("status", list(STATUS_BADGE_CLASSES))
def test_every_session_status_badge_reads(status):
    text, background, origins = _paint("beam", f"badge {STATUS_BADGE_CLASSES[status]}")
    assert branding.contrast(text[0], background[0]) >= 4.5, origins


def test_a_confirmed_session_stands_apart_from_a_draft():
    """Info and secondary are both Night greys, so Confirmed read as Draft
    in the session table. Confirmed is light green instead."""
    _, confirmed, _ = _paint(
        "beam", f"badge {STATUS_BADGE_CLASSES[SessionStatus.CONFIRMED]}"
    )
    _, draft, _ = _paint("beam", f"badge {STATUS_BADGE_CLASSES[SessionStatus.DRAFT]}")
    assert branding.contrast(confirmed[0], draft[0]) >= 3


def test_no_tone_badge_paints_its_text_over():
    """With the badge's text now set per tone, a text-dark or text-white
    beside a plain bg-* tone would win and undo it; such a badge uses the
    text-bg-* form instead."""
    root = Path(finders.find("css")).parent.parent.parent
    paired = re.compile(
        r'class="badge[^"]*\bbg-(?:primary|success|info|warning)\b[^"]*'
        r"\btext-(?:dark|white)\b"
    )
    found = [
        f"{path.relative_to(root)}: {match.group(0)!r}"
        for folder in [root / "templates", *root.glob("*/templates")]
        for path in folder.rglob("*.html")
        for match in paired.finditer(path.read_text())
    ]
    assert found == []


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


def test_toasts_stay_put_under_reduced_motion():
    """base.css cuts every animation to 0.01ms under "Reduce motion"; the
    toast hides itself through an animation, so without its own rule there
    it would vanish at once."""
    css = Path(finders.find("css/portal.css")).read_text()
    assert "animation: portal-toast-fade" in css
    blocks = re.findall(
        r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S
    )
    assert any(
        re.search(r"\.portal-toast \{\s*animation: none;", block) for block in blocks
    ), blocks


def test_alerts_leave_the_status_glyph_to_the_stylesheet():
    """portal.css draws a status glyph before every alert; an alert that
    opens with an icon of its own, straight away or inside its heading,
    would show two."""
    root = Path(finders.find("css")).parent.parent.parent
    opens_with_an_icon = re.compile(
        r'<div class="alert[^"]*"[^>]*>\s*(<(h[1-6]|strong|span)[^>]*>\s*)?'
        r'<i class="icon-'
    )
    doubled = [
        f"{path.relative_to(root)}: {found.group(0)!r}"
        for path in (root / "templates").rglob("*.html")
        for found in opens_with_an_icon.finditer(path.read_text())
    ]
    assert doubled == []


def test_compact_bootstrap_variants_keep_their_density():
    """The people-row spacing and the 44px control height are for the
    ordinary table and control; table-sm, form-control-sm and form-select-sm
    tie Bootstrap's own rules on specificity and would lose to them."""
    css = Path(finders.find("css/portal.css")).read_text()
    assert ".table:not(.table-sm) td {" in css
    assert ".table td {" not in css
    assert ".form-control:not(.form-control-sm):not(.input-group-sm > *)," in css
    assert (
        ".form-select:not(.form-select-sm):not(.input-group-sm > *) {\n"
        "    min-height: var(--control-h-md);"
    ) in css


def test_no_font_file_ships_twice_under_another_name():
    """The upright faces are variable fonts; Google served the same bytes
    for each weight asked, so one file per family and subset is enough."""
    fonts = Path(finders.find("fonts"))
    digests = {}
    for path in sorted(fonts.glob("*.woff2")):
        digests.setdefault(hashlib.md5(path.read_bytes()).hexdigest(), []).append(
            path.name
        )
    assert all(len(names) == 1 for names in digests.values()), digests
    css = (TOKENS / "fonts.css").read_text()
    assert "font-weight: 600 800;" in css and "font-weight: 400 700;" in css
