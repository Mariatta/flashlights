# Changelog

Each release publishes the image `ghcr.io/mariatta/flashlights:X.Y.Z`
(and `X.Y.Z-full`, with machine transcription) and a GitHub release with
the section below. Until 1.0, read every entry before upgrading; from 1.0,
a change to the [public API](docs/developer/community_apps.md#public-api)
for community apps is marked **Breaking**.
[Releasing](docs/developer/releasing.md) says how a release is made.

## 0.4.2 (unreleased)

- **Affiliation rows fit their card.** On the speaker profile, proposal,
  volunteer profile and account profile forms, the Remove checkbox and its
  label spilled past the card border. They now sit in a column sized to
  fit them, and the speaker profile form fills the content column instead
  of two thirds of it.
- **Code of Conduct and Terms of Service on every page.** The footer's
  About group (Code of Conduct, Terms of Service, Documentation) showed only
  on the signed-out landing page, so a signed-in person had no link to
  either. Every page now has it. The Sponsorship group (prospectus, donate)
  stays on the landing page.
- **Status badges are readable.** A speaker's "Confirmed" session showed
  black text on dark grey. Four badge colours kept Bootstrap's text colour
  on the portal's own backgrounds: confirmed, shared and the volunteer
  application badges (dark on grey), published, approved and other green
  badges (white on green, just short of readable), scheduled and the team
  counts (white on the accent, unreadable on a light accent), and a sponsor
  awaiting a response and the team's pending counts (white on orange). Each
  now has a text colour that reads on its background. A confirmed
  session's badge is light green, short of the solid green of a published
  session, so it no longer looks like a draft. The shared media, volunteer
  application and language badges, and an accepted or invoiced sponsor,
  are outlined.
- **"Propose another session" is a solid button.** On the speaker
  dashboard and My sessions pages it was an outline button, easier to miss
  than the filled "Open my checklist" on the dashboard. It is now filled
  too.

## 0.4.1 (2026-11-06)

- **A fresh database migrates again.** On 0.4.0, `migrate` on an empty
  database stopped in the sponsorship app with "cannot drop column id ...
  because other objects depend on it": Django 6.0 no longer drops a column
  with CASCADE, and an early migration swapped the primary key while a
  many-to-many table and a foreign key still pointed at it. A replacement
  migration takes its place on a database that has not applied it, removing
  the two relations first and putting them back on the new key. A database
  past that point, every deployment that upgraded, records the replacement
  and runs nothing. CI now applies every migration to a fresh database, so
  this cannot pass unnoticed again.

## 0.4.0 (2026-11-06)

- **Django 6.0.** The framework moves from 5.2 to 6.0, so community apps
  built on the image run on it too; Django 6.1 waits for a django-celery-beat
  release that allows it. Nothing changes for a deployment. A community app
  checks its own code against the
  [6.0 release notes](https://docs.djangoproject.com/en/6.0/releases/6.0/)
  before pinning this image: `format_html()` without arguments, the `check`
  keyword of `CheckConstraint` and positional arguments to `Model.save()`
  are gone, `forms.URLField` assumes https, and `ArrayField` and the other
  `django.contrib.postgres` fields now need that app installed, which the
  core does.
- **redis-py 8.** The Redis client in the image moves from 6.4 to 8.1.
  The Celery broker, the core's only use of it, is unchanged: kombu 5.7
  supports redis-py 8 and sets the connection timeouts itself. The broker
  must be Redis 6 or newer: redis-py 8 opens every connection with the
  `HELLO` command, which Redis 5 does not have. A community app that talks
  to Redis directly reads the
  [7.0](https://github.com/redis/redis-py/releases/tag/v7.0.0) and
  [8.0](https://github.com/redis/redis-py/releases/tag/v8.0.0) release
  notes before pinning this image: RESP3 is the wire protocol by default,
  with the old response shapes kept, socket timeouts default to five
  seconds, and the return type hints changed.
- **sqlparse 0.6.1.** The SQL formatter Django uses moves from 0.5.3 to
  0.6.1, which closes several denial-of-service advisories in parsing and
  formatting. Django only hands it its own migration and debug SQL, so
  nothing changes for a deployment. Its maintainer has announced the end of
  the project's maintenance with this release, so no further fixes are
  expected from it.
- **A long side rail scrolls on its own.** On desktop the rail is pinned
  beside the page, and one taller than the window kept its lower items
  below the fold until the page itself was scrolled to its end. The rail
  is now capped at the window's height and scrolls within it.

## 0.3.1 (2026-11-05)

- **The image is back on Python 3.14.** 0.3.0 moved it to 3.15, and its
  slim images run that version, but the full flavour with machine
  transcription did not build: faster-whisper needs onnxruntime, which has
  no wheel for 3.15 yet. So 0.3.0 has slim images only, and no GitHub
  release. Both flavours run 3.14 until onnxruntime catches up, and
  Dependabot's bump to 3.15 is held back with the reason beside the rule.

## 0.3.0 (2026-11-05)

- **The image runs Python 3.15.** Community apps built from it get the same
  interpreter.
- **The vendored libraries move up:** jQuery 4.0, Bootstrap 5.3, Select2
  4.1.0, htmx 2.0.11 and Chart.js 4.6. jQuery 4 dropped utilities such as
  `$.isArray`, `$.camelCase` and `$.trim`; a community app whose own
  scripts call them replaces those calls before pinning this image.
- **Organizers add their own questions to the proposal form.** Under
  Organize, Proposal questions, an edition asks anything beyond the fixed
  fields: about the session (asked per proposal, editable by the proposer
  while it waits) or about the speaker (asked once per person, on the form
  and on the speaker profile). Nine kinds of question: short and long text,
  yes or no, a box to tick, one or several choices from a list, a link,
  links one per line, a number. Each question says who reads the answer
  (organizers only, organizers and proposal reviewers, or everyone on the
  public program) and the form tells the person answering the same thing.
  Answers show on the proposal queue, the session page and the presenter
  page; public ones join the public API as `answers`. Questions can be
  copied from another edition, and "start next year" carries them over. A
  question with answers is switched off rather than deleted.
- **Affiliations reach speakers and the account page.** The affiliation
  rows that volunteers already keep are edited on Update profile, on My
  speaker profile and in the About you half of the proposal form, and shown
  to organizers on the proposal queue and the presenter page. They stay off
  the public program. The affiliation rows, which the volunteer form already
  had, now carry the form's styling instead of bare browser inputs.
- **Prerequisites and language are the edition's choice.** Two switches at
  the top of Proposal questions take either built-in field off the proposal
  form, the session forms, the session pages and the public API, where an
  unasked language prints null. Both stay on unless switched off.
- **The organizer's session page shows every description heading.** Summary,
  outline, prerequisites and audience each keep their heading when empty, so
  a reviewer sees what a proposer left out; the answers to the proposal
  questions follow them, inside the description.
- **A speaker's home page is about speaking.** Signing in used to open the
  volunteer hub for everyone who was not an organizer or a confirmed speaker,
  so a person who had created an account from the proposal form was greeted
  with "Create my volunteer profile", with their proposal below it; a speaker
  whose volunteer application had been declined saw that answer as their
  home. Now a proposal waiting for an answer opens **My proposals**, a
  speaker opens their dashboard unless they also volunteer this year, and an
  account that has done neither while proposals are open gets a page
  offering both ways to take part. A declined or withdrawn volunteer
  application no longer decides where a speaker or proposer lands. A
  **Proposals** tab stands in for **Speaking** until the proposal is
  accepted, and a proposer who does not volunteer sees their proposals on a
  page of their own instead of inside the volunteering rail.
- **The agreements page is styled.** An account that had not yet agreed to
  the Code of Conduct and the Terms of Service was sent to the page that
  asks, and so was its request for `/theme.css`, the stylesheet that
  carries the instance's accent. The browser got HTML in place of CSS, and
  "Agree and continue" rendered as bare text. The gate now lets the theme
  stylesheet, the icons and the share card through.
- **The pages say "your profile".** The agreements page asks "everyone
  with an account" rather than "a portal account". The profile form says
  "Update your profile" rather than "Edit your Portal Profile"; its
  breadcrumb, the account rail and every link to it say "Update profile";
  and the profile page says "Your profile".
- **The share card shows the Flashlights mark.** The mark's beam and
  lights are Beam yellow, so on the Beam accent, the default, a link
  preview showed only the handle. The lockup now sits on a Night band
  along the bottom of the card, as the site footer carries it, and the
  beam keeps its fade.
- **The footer's Flashlights lockup links to flashlights.app.** The
  "Source code" link beside it still goes to the repository.
- **A chosen radio button fills.** It was a Night ring with a Night dot,
  hard to tell from the empty ring beside it. It is now a Night disc with
  a Beam dot, the same fill as a ticked checkbox.

## 0.2.0 (2026-10-22)

- **A health route for the hosts' probes.** `GET /_health/` answers `200
  ok` before the `Host` header is checked and without a database query, so
  Cabotage (whose default probe path it is), Azure Container Apps (the
  template now declares startup, readiness and liveness probes against it)
  and any proxy or uptime monitor can probe the web process without a
  hostname and without rendering a page; the compose template's `web`
  service carries the same check. gunicorn keeps the probes out of the
  access log.

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
