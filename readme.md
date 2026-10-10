# Flashlights

*Tiny Little Flashlights*: the back-of-house platform for events, summits and meetups.

Flashlights runs the parts of an event nobody in the audience sees: the call
for proposals, speakers and their files, volunteers and teams, sponsors, the
schedule, and the emails that hold it all together. One instance serves one
community, edition after edition; each instance takes its name, colours,
logo and policy links from the environment (see `portal/branding.py`).

Flashlights is derived from the
[PyLadiesCon portal](https://github.com/pyladies/pyladiescon-portal), which
remains the portal built for PyLadiesCon. Improvements flow in both
directions through ordinary pull requests. The name is a nod to the Darren
Hayes song.

## Instance identity

| Variable | What it sets | Default |
|---|---|---|
| `SITE_TITLE` | Event or community name; page titles, Open Graph, email subjects | `Flashlights` |
| `SITE_SHORT_NAME` | Navbar wordmark | the title |
| `SITE_DESCRIPTION` | Open Graph description | "<title>: the organisers' portal" |
| `SITE_LOGO`, `SITE_FAVICON`, `SITE_OG_IMAGE` | Absolute URLs. Unset, a favicon (SVG plus PNG twins for Safari and iOS) and a share card are generated from the title and the primary colour | unset |
| `BRAND_PRESET` | The accent: `beam`, `teal`, `copper`, `indigo` or `raspberry`. The chrome (Night, Paper, type) is fixed | `beam` |
| `BRAND_PRIMARY` | A custom `#rrggbb` accent; the ink on it (Night or white), its text shade on Paper and the hover and press shades are derived | unset |
| `DOCS_URL`, `TERMS_URL` | Documentation and terms of service links; left out when unset | unset |
| `VOLUNTEERING_ENABLED` | `false` hides the Volunteer hub, its nav and organizer entries and the landing section; its pages answer 404 | `true` |
| `SPONSORSHIP_ENABLED` | `false` hides sponsors, tiers, donations, their stats and dashboard tiles; its pages answer 404 | `true` |
| `STATS_PUBLIC` | `false` takes the public stats pages (stats, year comparison, JSON, gallery) off the site | `true` |
| `PRETIX_ORGANIZER` | The Pretix organizer slug whose webhooks and orders this instance accepts | unset |
| `SPONSORSHIP_EMAIL`, `ACCOUNTING_EMAIL` | Who receives a sponsorship contract request; skipped when both are unset | unset |

The Code of Conduct, sponsorship prospectus, donation and schedule links come
from the active edition's record; a link that is not set is not shown. The
edition's "Taking volunteer applications" flag decides whether the landing
page advertises volunteering at all; off, the team keeps its hub and the
public page only offers sign in. Stats sections follow the features:
volunteer stats with volunteering, sponsorship and donation stats with
sponsorship, attendee stats only when `PRETIX_API_TOKEN` is set.

## Local Dev setup

Go to [the Dev setup documentation page](docs/developer/setup.md).
