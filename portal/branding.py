"""Instance identity: name, colours, logo, favicon, share image, doc links.

Read once from the environment at boot. The keys mirror the Popular
theme's ``SITE`` and ``BRAND`` config so a community sets the same values
for its public site and its Flashlights instance:

``SITE_TITLE``, ``SITE_SHORT_NAME``, ``SITE_DESCRIPTION``, ``SITE_LOGO``,
``SITE_FAVICON``, ``SITE_OG_IMAGE``, ``BRAND_PRESET``, ``BRAND_PRIMARY``,
``DOCS_URL``, ``TERMS_URL``.

Colours: the design system fixes the chrome (Night, Paper,
type, spacing); the accent is the one instance colour. It comes from a
preset, ``beam`` by default, or from ``BRAND_PRIMARY`` as the escape hatch.
The ink on the accent is chosen by contrast, Night on a light accent and
white on a dark one, and the hover and press shades are derived in the
right direction. Every colour has an ink that reads: against Night or
against white, one of the two always clears 3:1, so nothing is refused.
There is no custom CSS and the fonts are fixed.
"""

import hashlib
import io
import math
import os
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

#: name -> (accent, hover, press). Beam is the design system's own palette;
#: teal, copper and indigo are the Popular theme's demo palettes; raspberry
#: is the upstream portal's heritage palette.
PRESETS = {
    "beam": ("#ffd43b", "#ffe27a", "#f2bd00"),
    "teal": ("#0f766e", "#0d5f59", "#0b4f4a"),
    "copper": ("#b45309", "#92400e", "#7c2d12"),
    "indigo": ("#4f46e5", "#4338ca", "#3730a3"),
    "raspberry": ("#ee264d", "#d11f42", "#c01f3f"),
}
#: A preset may pin the accent's text shade on Paper instead of deriving it:
#: Beam's is the design system's Beam 700.
PRESET_INKS = {"beam": "#7a5c00"}
DEFAULT_PRESET = "beam"
DEFAULT_TITLE = "Flashlights"

#: The design system's fixed neutrals; the accent is read against them.
NIGHT = "#0f0f0d"
PAPER = "#f7f5ef"
WHITE = "#ffffff"

#: WCAG minimum for user-interface components and large text (filled
#: buttons), and for body text (accent-coloured text on Paper).
MIN_CONTRAST = 3.0
TEXT_CONTRAST = 4.5


def parse_hex(value):
    """``#rrggbb`` -> (r, g, b); anything else is a configuration error."""
    text = value.strip()
    if len(text) != 7 or text[0] != "#":
        raise ImproperlyConfigured(
            f"BRAND_PRIMARY must look like #rrggbb, not {value!r}"
        )
    try:
        return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))
    except ValueError:
        raise ImproperlyConfigured(
            f"BRAND_PRIMARY must look like #rrggbb, not {value!r}"
        ) from None


def _to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def _luminance(rgb):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio between two colours, given as RGB tuples."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_with_white(rgb):
    """WCAG contrast ratio between a colour and white."""
    return contrast(rgb, parse_hex(WHITE))


def darken(rgb, amount):
    """Mix a colour towards black by ``amount`` (0 keeps it, 1 is black)."""
    return tuple(round(c * (1 - amount)) for c in rgb)


def lighten(rgb, amount):
    """Mix a colour towards white by ``amount`` (0 keeps it, 1 is white)."""
    return tuple(round(c + (255 - c) * amount) for c in rgb)


def text_on(rgb):
    """The ink a filled accent carries: Night on a light colour, white on a
    dark one, whichever reads better. One of the two always clears 3:1."""
    return (
        NIGHT if contrast(rgb, parse_hex(NIGHT)) >= contrast_with_white(rgb) else WHITE
    )


def ink_on_paper(rgb):
    """The accent as a text colour on Paper: the accent itself when it reads,
    otherwise darkened until it does (Beam yellow becomes Beam 700)."""
    paper = parse_hex(PAPER)
    ink = rgb
    while contrast(ink, paper) < TEXT_CONTRAST and ink != (0, 0, 0):
        ink = darken(ink, 0.1)
    return _to_hex(ink)


def accent_shades(primary):
    """Hover and press shades for a custom accent: a light accent lightens
    on hover and darkens on press, a dark one darkens both ways."""
    rgb = parse_hex(primary)
    if text_on(rgb) == NIGHT:
        return _to_hex(lighten(rgb, 0.3)), _to_hex(darken(rgb, 0.1))
    return _to_hex(darken(rgb, 0.12)), _to_hex(darken(rgb, 0.2))


@dataclass(frozen=True)
class Brand:
    title: str
    short_name: str
    description: str
    logo: str
    favicon: str
    og_image: str
    preset: str
    primary: str
    primary_hover: str
    primary_active: str
    #: The accent as text on Paper, and the text on a filled accent.
    accent_ink: str
    text_on_accent: str
    docs_url: str
    terms_url: str

    @property
    def initial(self):
        """One character for the generated favicon."""
        return self.short_name.strip()[:1].upper() or "F"

    @property
    def slug(self):
        """The short name as a path-safe token: media export folders and
        archive names start with it."""
        return slugify(self.short_name) or "flashlights"

    def rgb(self, name):
        """``'r, g, b'`` for a colour field, the form Bootstrap's ``-rgb`` vars take."""
        return ", ".join(str(c) for c in parse_hex(getattr(self, name)))

    def theme_css(self):
        """The stylesheet ``portal.css`` builds on: the accent and its
        shades as variables, under the design system's names and the
        portal's older ``--brand-*`` names, plus Bootstrap's."""
        night_rgb = ", ".join(str(c) for c in parse_hex(NIGHT))
        return (
            ":root {\n"
            f"    --accent: {self.primary};\n"
            f"    --accent-rgb: {self.rgb('primary')};\n"
            f"    --accent-hover: {self.primary_hover};\n"
            f"    --accent-hover-rgb: {self.rgb('primary_hover')};\n"
            f"    --accent-press: {self.primary_active};\n"
            f"    --accent-ink: {self.accent_ink};\n"
            f"    --text-on-accent: {self.text_on_accent};\n"
            "    --focus-halo: var(--accent);\n"
            "    --brand-primary: var(--accent);\n"
            "    --brand-primary-rgb: var(--accent-rgb);\n"
            "    --brand-primary-hover: var(--accent-hover);\n"
            "    --brand-primary-hover-rgb: var(--accent-hover-rgb);\n"
            "    --brand-primary-active: var(--accent-press);\n"
            f"    --brand-ink: {NIGHT};\n"
            f"    --brand-ink-rgb: {night_rgb};\n"
            "    --bs-primary: var(--accent);\n"
            "    --bs-primary-rgb: var(--accent-rgb);\n"
            "    --bs-primary-text-emphasis: var(--accent-ink);\n"
            "    --bs-dark: var(--brand-ink);\n"
            "    --bs-dark-rgb: var(--brand-ink-rgb);\n"
            "    --bs-link-color: var(--accent-ink);\n"
            "    --bs-link-color-rgb: var(--accent-rgb);\n"
            "    --bs-link-hover-color: var(--accent-press);\n"
            "    --bs-link-hover-color-rgb: var(--accent-hover-rgb);\n"
            "}\n"
        )

    @property
    def version(self):
        """Short content hash; the theme, favicon and share card URLs carry
        it so caches drop the old colours or wording the moment the
        environment changes."""
        source = self.theme_css() + self.initial + self.title + self.description
        return hashlib.sha256(source.encode()).hexdigest()[:12]

    def favicon_svg(self):
        """A rounded square in the primary colour with the title's initial."""
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            f'<rect width="64" height="64" rx="14" fill="{self.primary}"/>'
            '<text x="32" y="44" text-anchor="middle" font-family="system-ui, sans-serif" '
            f'font-size="38" font-weight="700" fill="{self.text_on_accent}">{self.initial}</text>'
            "</svg>"
        )

    def favicon_png(self, size=32):
        """The SVG favicon's twin as a PNG, for Safari's tab icon and the iOS
        home screen (180px), which do not read SVG."""
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (0, 0, size - 1, size - 1), radius=round(size * 14 / 64), fill=self.primary
        )
        _draw_centered(
            draw,
            self.initial,
            size / 2,
            size / 2,
            round(size * 0.6),
            ink=self.text_on_accent,
        )
        return _png_bytes(image)

    def share_card_png(self):
        """The default Open Graph image: primary background, the title and
        description, and a small Flashlights mark. 1200 by 630, the size
        every social network reads."""
        width, height = 1200, 630
        image = Image.new("RGB", (width, height), self.primary)
        draw = ImageDraw.Draw(image)
        ink = self.text_on_accent
        _draw_centered(
            draw, self.title, width / 2, height * 0.42, 96, max_width=1080, ink=ink
        )
        _draw_centered(
            draw,
            self.description,
            width / 2,
            height * 0.62,
            40,
            max_width=1080,
            ink=ink,
        )
        # The small Flashlights mark with its name, bottom centre.
        _draw_mark(draw, width / 2 - 78, height - 56, 56, ink)
        _draw_centered(
            draw, "Flashlights", width / 2 + 16, height - 56, 28, opacity=170, ink=ink
        )
        return _png_bytes(image)


def _draw_mark(draw, cx, cy, size, ink):
    """The torch mark (Wordmark spec, simplified) centred on (cx, cy):
    handle and lens in ``ink``, beam and one light in Beam yellow, the whole
    rotated 32 degrees up like the SVG."""
    beam = (255, 212, 59)
    angle = math.radians(-32)
    cos, sin = math.cos(angle), math.sin(angle)

    def at(x, y):
        # Design coordinates are 0..100 around (50, 50); scale to ``size``.
        dx, dy = (x - 50) / 100 * size, (y - 50) / 100 * size
        return (cx + dx * cos - dy * sin, cy + dx * sin + dy * cos)

    draw.polygon([at(52, 40), at(100, 18), at(100, 82), at(52, 60)], fill=beam + (60,))
    draw.polygon([at(0, 40), at(34, 40), at(34, 60), at(0, 60)], fill=parse_hex(ink))
    draw.polygon([at(32, 40), at(48, 34), at(48, 66), at(32, 60)], fill=parse_hex(ink))
    draw.polygon([at(48, 34), at(52, 34), at(52, 66), at(48, 66)], fill=beam)
    lx, ly = at(80, 44)
    r = size * 0.05
    draw.ellipse((lx - r, ly - r, lx + r, ly + r), fill=beam)


def _font(size):
    """Pillow's bundled scalable font: the only one an image is guaranteed
    to have, whatever the host."""
    return ImageFont.load_default(size=size)


def _draw_centered(draw, text, x, y, size, max_width=None, opacity=255, ink=WHITE):
    """Text in ``ink`` centred on (x, y), shrunk until it fits ``max_width``."""
    font = _font(size)
    if max_width:
        while size > 16 and draw.textlength(text, font=font) > max_width:
            size -= 4
            font = _font(size)
    draw.text((x, y), text, font=font, fill=parse_hex(ink) + (opacity,), anchor="mm")


def _png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def from_env(environ=None):
    """Build the instance's :class:`Brand` from the environment."""
    env = os.environ if environ is None else environ
    title = env.get("SITE_TITLE", "").strip() or DEFAULT_TITLE
    short_name = env.get("SITE_SHORT_NAME", "").strip() or title
    preset = env.get("BRAND_PRESET", "").strip() or DEFAULT_PRESET
    if preset not in PRESETS:
        raise ImproperlyConfigured(
            f"BRAND_PRESET {preset!r} is not one of: {', '.join(sorted(PRESETS))}"
        )
    primary, hover, active = PRESETS[preset]
    custom = env.get("BRAND_PRIMARY", "").strip()
    if custom:
        primary = _to_hex(parse_hex(custom))
        hover, active = accent_shades(primary)
    rgb = parse_hex(primary)
    return Brand(
        title=title,
        short_name=short_name,
        description=env.get("SITE_DESCRIPTION", "").strip()
        or f"{title}: the organisers' portal",
        logo=env.get("SITE_LOGO", "").strip(),
        favicon=env.get("SITE_FAVICON", "").strip(),
        og_image=env.get("SITE_OG_IMAGE", "").strip(),
        preset=preset,
        primary=primary,
        primary_hover=hover,
        primary_active=active,
        accent_ink=(PRESET_INKS.get(preset) if not custom else None)
        or ink_on_paper(rgb),
        text_on_accent=text_on(rgb),
        docs_url=env.get("DOCS_URL", "").strip(),
        terms_url=env.get("TERMS_URL", "").strip(),
    )
