# Changelog

Each release publishes the image `ghcr.io/mariatta/flashlights:X.Y.Z`
(and `X.Y.Z-full`, with machine transcription) and a GitHub release with
the section below. Until 1.0, read every entry before upgrading; from 1.0,
a change to the [public API](docs/developer/community_apps.md#public-api)
for community apps is marked **Breaking**.
[Releasing](docs/developer/releasing.md) says how a release is made.

## 0.1.0 (2026-10-21)

The first release of Flashlights, derived from the
[PyLadiesCon portal](https://github.com/pyladies/pyladiescon-portal).

- **Identity is configuration.** The name, colours, logo, favicon, share
  image and links come from environment variables, so one image serves any
  community. The design system (tokens, self-hosted fonts and icons)
  restyles every page.
- **One instance per community, an edition per event.** Editions are one
  event a year or a series of dates, with venues and rooms, a format (in
  person, online or hybrid), recordings and community chat as settings,
  and the next edition planned while the current one runs.
- **Permissions through teams.** Each team grants permissions from a
  catalogue, with presets such as Organizers, Program, Sponsorship and
  Proposal reviewers; the settings organisers need left the Django admin.
- **Speakers.** Invitations, profiles, sessions, two-sided checklists with
  reminders, the schedule, video and file uploads, and a public program
  widget and API.
- **Attendee records** from Pretix or a CSV export, for the stats.
- **Handles per person**: social links and pronouns belong to the account,
  and every form reads from them.
- **Runs on any host.** The boot contract (`web`, `worker`, `release`) and
  the environment reference cover Heroku and compatibles, Azure, Cabotage
  and a plain server; switches turn off volunteering, sponsorship and the
  public stats.
- **Community apps** add a Django app to the image with `EXTRA_APPS`, and
  may replace a core template or static file.
- **Documentation per release.** Each release publishes its own version
  of the docs at `https://docs.flashlights.app/X.Y.Z/`, and
  `latest/` follows the newest release.
- **Nothing loads from anywhere else.** Every script, stylesheet, font and
  chart is served by the instance itself, with Dependabot watching the
  vendored libraries. Sentry receives personal data only with
  `SENTRY_SEND_DEFAULT_PII` on.
- Free software under the GNU AGPL version 3, with a permission to run a
  modified copy for your own organisation's events.
