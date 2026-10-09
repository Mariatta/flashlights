"""Instance identity: name, colours, logo, favicon, share image, doc links.

Read once from the environment at boot (flashlights-architecture, decision
0004). The keys mirror the Popular theme's ``SITE`` and ``BRAND`` config so a
community sets the same values for its public site and its Flashlights
instance:

``SITE_TITLE``, ``SITE_SHORT_NAME``, ``SITE_DESCRIPTION``, ``SITE_LOGO``,
``SITE_FAVICON``, ``SITE_OG_IMAGE``, ``BRAND_PRESET``, ``BRAND_PRIMARY``,
``DOCS_URL``, ``TERMS_URL``.

Colours come from a preset, each checked for contrast once, with one custom
primary colour as the escape hatch; hover and active shades are derived from
it. A custom colour that cannot carry white text is refused at boot rather
than shipped. There is no custom CSS and the fonts are fixed.
"""

import hashlib
import io
import os
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

#: name -> (primary, hover, active, ink). The first three are the Popular
#: theme's demo palettes; raspberry is the upstream portal's heritage palette.
PRESETS = {
    "teal": ("#0f766e", "#0d5f59", "#0b4f4a", "#142a36"),
    "copper": ("#b45309", "#92400e", "#7c2d12", "#142a36"),
    "indigo": ("#4f46e5", "#4338ca", "#3730a3", "#142a36"),
    "raspberry": ("#ee264d", "#d11f42", "#c01f3f", "#152035"),
}
DEFAULT_PRESET = "teal"
DEFAULT_TITLE = "Flashlights"

#: WCAG minimum for user-interface components and large text, which is what
#: the primary colour carries: filled buttons with white labels.
MIN_CONTRAST = 3.0


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


def contrast_with_white(rgb):
    """WCAG contrast ratio between a colour and white."""
    return 1.05 / (_luminance(rgb) + 0.05)


def darken(rgb, amount):
    """Mix a colour towards black by ``amount`` (0 keeps it, 1 is black)."""
    return tuple(round(c * (1 - amount)) for c in rgb)


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
    ink: str
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
        """The stylesheet ``portal.css`` builds on: every brand colour as a variable."""
        return (
            ":root {\n"
            f"    --brand-primary: {self.primary};\n"
            f"    --brand-primary-rgb: {self.rgb('primary')};\n"
            f"    --brand-primary-hover: {self.primary_hover};\n"
            f"    --brand-primary-hover-rgb: {self.rgb('primary_hover')};\n"
            f"    --brand-primary-active: {self.primary_active};\n"
            f"    --brand-ink: {self.ink};\n"
            f"    --brand-ink-rgb: {self.rgb('ink')};\n"
            "    --bs-primary: var(--brand-primary);\n"
            "    --bs-primary-rgb: var(--brand-primary-rgb);\n"
            "    --bs-primary-text-emphasis: var(--brand-primary-active);\n"
            "    --bs-dark: var(--brand-ink);\n"
            "    --bs-dark-rgb: var(--brand-ink-rgb);\n"
            "    --bs-link-color: var(--brand-primary);\n"
            "    --bs-link-color-rgb: var(--brand-primary-rgb);\n"
            "    --bs-link-hover-color: var(--brand-primary-hover);\n"
            "    --bs-link-hover-color-rgb: var(--brand-primary-hover-rgb);\n"
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
            f'font-size="38" font-weight="700" fill="#fff">{self.initial}</text>'
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
        _draw_centered(draw, self.initial, size / 2, size / 2, round(size * 0.6))
        return _png_bytes(image)

    def share_card_png(self):
        """The default Open Graph image: primary background, the title and
        description, and a small Flashlights mark. 1200 by 630, the size
        every social network reads."""
        width, height = 1200, 630
        image = Image.new("RGB", (width, height), self.primary)
        draw = ImageDraw.Draw(image)
        _draw_centered(draw, self.title, width / 2, height * 0.42, 96, max_width=1080)
        _draw_centered(
            draw, self.description, width / 2, height * 0.62, 40, max_width=1080
        )
        _draw_centered(draw, "Flashlights", width / 2, height - 56, 28, opacity=170)
        return _png_bytes(image)


def _font(size):
    """Pillow's bundled scalable font: the only one an image is guaranteed
    to have, whatever the host."""
    return ImageFont.load_default(size=size)


def _draw_centered(draw, text, x, y, size, max_width=None, opacity=255):
    """White text centred on (x, y), shrunk until it fits ``max_width``."""
    font = _font(size)
    if max_width:
        while size > 16 and draw.textlength(text, font=font) > max_width:
            size -= 4
            font = _font(size)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity), anchor="mm")


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
    primary, hover, active, ink = PRESETS[preset]
    custom = env.get("BRAND_PRIMARY", "").strip()
    if custom:
        rgb = parse_hex(custom)
        ratio = contrast_with_white(rgb)
        if ratio < MIN_CONTRAST:
            raise ImproperlyConfigured(
                f"BRAND_PRIMARY {custom} has {ratio:.1f}:1 contrast against white; "
                f"white button text needs at least {MIN_CONTRAST:.0f}:1. Pick a darker colour."
            )
        primary = _to_hex(rgb)
        hover = _to_hex(darken(rgb, 0.12))
        active = _to_hex(darken(rgb, 0.2))
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
        ink=ink,
        docs_url=env.get("DOCS_URL", "").strip(),
        terms_url=env.get("TERMS_URL", "").strip(),
    )
