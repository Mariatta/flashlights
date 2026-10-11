# Design system

Flashlights has one look, fixed for every instance, and one colour an
instance chooses. The look is the design system in the private
architecture notes (`design/`, decision 0010); this page says how it maps
onto the code.

## Where things live

| Piece | Path |
|---|---|
| Entry stylesheet | `portal/static/css/flashlights.css` |
| Tokens (colours, type, spacing, effects, base) | `portal/static/css/tokens/*.css` |
| Fonts and the icon font, with licences | `portal/static/fonts/` |
| The instance's accent | `/theme.css`, rendered from the environment by `portal/branding.py` |
| Bootstrap re-themed and the portal's components | `portal/static/css/portal.css` |
| Flashlights' own mark | `portal/static/img/flashlights/`, `templates/portal/_flashlights_mark.html` |

`base.html` loads Bootstrap, then `flashlights.css`, then `theme.css`, then
`portal.css`. Nothing on a page is fetched from a third party except
Bootstrap itself.

## Tokens and variables

The tokens are CSS custom properties: `--night-950` to `--night-100`,
`--paper`, `--beam-200` to `--beam-700`, the status colours (`--ok-*`,
`--warn-*`, `--stop-*`) and the semantic aliases (`--surface-page`,
`--text-strong`, `--border-subtle`, and so on). Type is `--font-display`
(Bricolage Grotesque), `--font-body` (Atkinson Hyperlegible Next) and
`--font-mono` (Atkinson Hyperlegible Mono), with the roles `--type-display`,
`--type-h1` to `--type-h4`, `--type-body`, `--type-small`, `--type-eyebrow`
and `--type-mono`. Spacing is a 4px base (`--space-1` to `--space-9`), radii
are `--radius-sm` 4, `--radius-md` 8 and `--radius-lg` 14, controls are
`--control-h-md` 44px tall.

The accent is the only variable an instance changes: `--accent`,
`--accent-hover`, `--accent-press`, `--accent-ink` (the accent as text on
Paper) and `--text-on-accent` (Night or white, chosen by contrast). The
older `--brand-*` names and Bootstrap's `--bs-primary` alias it.

## Rules that hold

- Borders over shadows. Cards are white with a 1px Night 200 border and
  radius 14; the one important element on a page gets a 2px Night border
  (`.card-strong`). An interactive card lifts 2px with the hard shadow.
- Controls have 2px borders, radius 8 and are 44px tall. Focus is the
  two-tone ring (`--ring-focus`).
- Status always pairs colour with an icon and a word: alerts draw their
  icon, chips carry a label, checklist boxes carry a glyph.
- Beam is never text on Paper; accent-coloured text uses `--accent-ink`.
- Night surfaces (navbar, footer, hero, a live session) carry the beam
  glow (`--beam-glow`), tinted by the accent.
- Icons are Lucide, as `<i class="icon-<name>" aria-hidden="true">`, 1.1em
  next to text; `icon-fw`, `icon-xs`, `icon-lg` and `icon-2x` size them.
  Icon-only buttons need an `aria-label`.
- Dates in chips are mono and day-first with the month in capitals,
  `12 NOV`, and schedules state their time zone.

## Components and their classes

| Spec | In the code |
|---|---|
| Navbar | `base.html`; `.edition-chip`, `.avatar-initial`, the active tab's underline |
| SideRail | `base_sidebar.html` and `_sidebar_item.html`; `.app-sidebar .nav-pills` |
| Breadcrumbs, Tabs | `.breadcrumb`, `.nav-tabs` |
| Toast, Alert, Progress | `_toast_messages.html` and `_toast.html`; `.alert-*` incl. `.alert-beam`; `.progress` |
| Input, Select, Checkbox, Switch | `.form-control`, `.form-select`, `.form-check`, `.form-switch`; allauth's elements in `templates/allauth/elements/` |
| Card, StatCard | `.card`, `.card-strong`, `.stat-card` |
| AttentionItem | `.attention-list`, `.attention-item`, `.attention-tile` |
| ChecklistItem | `speakers/_checklist_item.html`; `.checklist-*` |
| SessionCard, ScheduleCard, GlanceTile | `.session-card`, `.schedule-card`, `.glance-tile` |
| PersonRow | `portal/people.py` (`person_cell`, `status_chip`); `.person-*`, `.status-chip` |
| Wordmark | `_flashlights_mark.html`; `.flashlights-lockup` |
| Eyebrow | `.eyebrow` |

## Voice

Plain, warm, specific. "We" are the organizers, "you" is the reader; never
"the user". Sentence case everywhere, buttons start with a verb, counts lead
in bold, no exclamation marks, no emoji. Gender-neutral wording.
