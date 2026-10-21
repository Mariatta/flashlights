# Flashlights

*Tiny Little Flashlights*: the organizers' portal for events, summits and meetups.

Flashlights runs the parts of an event nobody in the audience sees: a
lightweight speaker intake, the speakers and their files, volunteers and
teams, sponsors, the schedule, and the emails that hold it all together. The
intake is not a call for proposals system: people propose a session and you
say yes or no, or you invite the speakers you have already chosen. One
instance serves one community, edition after edition; each instance takes its name, colours, logo and policy links from
the environment (see `portal/branding.py`).

Flashlights is derived from the
[PyLadiesCon portal](https://github.com/pyladies/pyladiescon-portal), which
remains the portal built for PyLadiesCon. That portal was built for one
event's needs; Flashlights keeps its core, moves what differs between
communities into configuration and each community's own app (see
`docs/developer/community_apps.md`), and is meant to be self-hosted, one
instance per community. It is not a hosting service. The name is a nod to
the Darren Hayes song.

## Licence and contributions

Flashlights is free software under the GNU Affero General Public License
version 3, with one additional permission: an organisation may run a
modified Flashlights for its own events, including its chapters, departments
and member groups, without publishing its changes. Hosting Flashlights as a
service for others is not covered by that permission. Code from the
PyLadiesCon portal stays under the MIT License, and so does the embeddable
program widget. The details are in `LICENSE` and `LICENSE-MIT`.

Flashlights is published for use and study, and does not take code
contributions. Bug reports and ideas are welcome as issues; a suggestion may
be implemented, but code from pull requests is not merged. Report security
problems privately, as described in `SECURITY.md`.

## What an instance needs

Four services: Postgres, Redis, an S3-compatible bucket (any provider) and
an SMTP server (any provider). In production the boot fails at once,
naming every missing variable, when one of these is unset:

| Variable | What it is |
|---|---|
| `SECRET_KEY` | Django's secret key (required everywhere) |
| `DJANGO_ALLOWED_HOSTS` | The hostnames the portal answers on, comma-separated |
| `DATABASE_URL` | The Postgres connection URL |
| `CELERY_BROKER_URL` or `REDIS_URL` | The Redis URL the worker and beat share |
| `FERNET_KEY` or `FERNET_KEYS` | The key for fields encrypted at rest |
| `DJANGO_EMAIL_HOST` or `EMAIL_URL` | The SMTP server (`EMAIL_URL` is `smtp://user:password@host:port/?tls=true`) |
| `DJANGO_DEFAULT_FROM_EMAIL` | The address the portal's email comes from |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL` | The bucket, through the S3 API; `USE_OBJECT_STORAGE=true` turns it on (`USE_SPACES` still works) |

With `DEBUG` on, email prints to the console and files stay on disk, so
only `SECRET_KEY` is required. The full list, with every optional variable,
is in `docs/developer/environment.md`.

## Instance identity

| Variable | What it sets | Default |
|---|---|---|
| `SITE_TITLE` | Event or community name; page titles, Open Graph, email subjects | `Flashlights` |
| `SITE_SHORT_NAME` | Navbar wordmark | the title |
| `SITE_DESCRIPTION` | Open Graph description | "<title>: the organisers' portal" |
| `SITE_LOGO`, `SITE_FAVICON`, `SITE_OG_IMAGE` | Absolute URLs. Unset, a favicon (SVG plus PNG twins for Safari and iOS) and a share card are generated from the title and the primary colour | unset |
| `BRAND_PRESET` | The accent: `beam`, `teal`, `copper`, `indigo` or `raspberry`. The chrome (Night, Paper, type) is fixed | `beam` |
| `BRAND_PRIMARY` | A custom `#rrggbb` accent; the ink on it (Night or white), its text shade on Paper and the hover and press shades are derived | unset |
| `DOCS_URL` | The help links: your community's own docs when it has some, else the core docs for this image's version. The landing's team descriptions link and the volunteer resources card appear only when it is set | the core docs for this version |
| `TERMS_URL` | The terms of service link; left out when unset | unset |
| `VOLUNTEERING_ENABLED` | `false` hides the Volunteer hub, its nav and organizer entries and the landing section; its pages answer 404 | `true` |
| `SPONSORSHIP_ENABLED` | `false` hides sponsors, tiers, donations, their stats and dashboard tiles; its pages answer 404 | `true` |
| `STATS_PUBLIC` | `false` takes the public stats pages (stats, year comparison, JSON) off the site | `true` |
| `SPONSORSHIP_EMAIL`, `ACCOUNTING_EMAIL` | Who receives a sponsorship contract request; skipped when both are unset | unset |
| `EXTRA_APPS` | Django apps a community adds to the core, comma-separated; they go first, their templates and static files win, and their URLs are included under a prefix (`docs/developer/community_apps.md`) | unset |

The Code of Conduct, sponsorship prospectus, donation and schedule links come
from the active edition's record; a link that is not set is not shown. The
edition's "Taking volunteer applications" flag decides whether the landing
page advertises volunteering at all; off, the team keeps its hub and the
public page only offers sign in. Stats sections follow the features:
volunteer stats with volunteering, sponsorship and donation stats with
sponsorship, attendee stats once the active edition has ticketing set up on
its Tickets page (a Pretix shop or CSV imports) or has registrations.

## Local Dev setup

Go to [the Dev setup documentation page](docs/developer/setup.md).
