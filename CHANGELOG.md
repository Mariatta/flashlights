# Changelog

Each release publishes the image `ghcr.io/mariatta/flashlights:X.Y.Z`
(and `X.Y.Z-full`, with machine transcription) and a GitHub release with
the section below. Until 1.0, read every entry before upgrading; from 1.0,
a change to the [public API](docs/developer/community_apps.md#public-api)
for community apps is marked **Breaking**.
[Releasing](docs/developer/releasing.md) says how a release is made.

## 0.3.0 (unreleased)

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
