---
title: Third-party code and services
description: Why every page is served by the instance itself, what is vendored, and how its updates arrive
---

# Third-party code and services

Flashlights holds people's names, email addresses, photos and talks, and the
people using it never chose the tools it is built with. So it follows one
rule: **a third-party service only when it is absolutely needed and no
adequate open-source, self-hosted option exists.** For the browser that
means:

- **Every page is served by the instance itself.** Scripts, stylesheets,
  fonts, icons, charts and images come from the instance's own `/static/`,
  so opening a page tells no other company who you are, what browser you
  use or which page you are on.
- **No analytics, no advertising, no third-party cookies.** The only cookies
  are the instance's own, which keep you signed in and protect its forms.
- **No hosted CAPTCHA, no embedded fonts, no CDN.** The signup challenge is
  generated on the server ([Signup Abuse Protection](../architecture/signup-abuse-protection.md)
  explains that choice), and the fonts ship with the code
  ([Design System](design.md)).

Links to other sites (a speaker's GitHub, the source code, a calendar
service) are only links: nothing loads until someone follows one.

Tests hold the rule in place: `tests/portal/test_vendored_assets.py` fails
when any template loads a script, stylesheet, image or frame from another
server, and `tests/portal/test_design_tokens.py` does the same for the
stylesheets.

## What is vendored

The browser libraries live in `portal/static/vendor/`, each with its
licence:

| Library | Used for |
|---|---|
| [Bootstrap](https://getbootstrap.com/) | Layout and components on every page |
| [htmx](https://htmx.org/) | Checklists and the organize pages, which update in place |
| [Chart.js](https://www.chartjs.org/) | The charts on the stats pages and the maintenance page, drawn by `portal/static/js/charts.js` in the design system's colours |
| [jQuery](https://jquery.com/) and [Select2](https://select2.org/) | The searchable multi-selects on the volunteer form |

`package.json` pins each version exactly. The files are copied out of npm
by `frontend/vendor.mjs` and committed, so running, testing or deploying
Flashlights needs no Node. `frontend/vendored.json` records each library's
version and the sha256 of every copied file.

## How updates arrive

Dependabot (`.github/dependabot.yml`) checks once a week and opens a pull
request for each new release of a browser library, a Python package or a
GitHub Action. GitHub's security advisories cover the same pins, so a
known vulnerability shows up as an alert as well as a pull request.

A pull request for a browser library changes `package.json` and
`package-lock.json` only, and its tests fail until the new files are
copied. To finish it:

```bash
git switch <the dependabot branch>
npm ci
npm run vendor
git add portal/static/vendor frontend/vendored.json
git commit -m "Vendor <library> <version>"
git push
```

Then look at the pages that use the library before merging. A major
version (Bootstrap 6, jQuery 4) is worth a branch of its own.

Without the GitHub repository, the same checks run locally:

```bash
npm outdated        # newer releases of the browser libraries
npm audit           # known vulnerabilities in them
pip list --outdated # newer Python packages, in the portal's interpreter
pip-audit -r requirements-app.txt  # after pip install pip-audit
```

## Adding a library

1. Make sure the page really needs it. A few lines of the portal's own
   JavaScript, or HTML and CSS, are usually enough.
2. `npm install --save-dev --save-exact <package>@<version>`.
3. Add it to `LIBRARIES` in `frontend/vendor.mjs`: its folder under
   `portal/static/vendor/`, the built files the page loads, any source map
   those files name, and the licence file.
4. `npm run vendor`, then link the files with `{% static %}`.

A community app follows the same rule: its scripts and styles go in its own
`static/` folder ([Community apps](community_apps.md)), not on a CDN.

## Services an instance talks to

These are server to server. No visitor's browser contacts them, and none
of them sets a cookie on a visitor.

| Service | When | What it receives |
|---|---|---|
| The email provider | Always | Each email Flashlights sends: recipient, subject, body. Open and click tracking is a setting in the provider's account; keep it off |
| Object storage | `USE_OBJECT_STORAGE` on | Uploaded files. Headshots and logos in the public bucket are served from the bucket's address, the operator's own storage rather than a tracker |
| Pretix | An edition has a Pretix organizer | Ticket and attendee lookups for that edition |
| Sentry | `SENTRY_SDK_DSN` set | Each error, with the stack trace and the address of the request that caused it. The signed-in person's details, IP address, request headers and cookies only with `SENTRY_SEND_DEFAULT_PII` on, which the instance's privacy notice then has to mention |

## Saying it to the people who use the instance

The [terms of service template](../policies/terms_of_use.md) has a
paragraph on this for organisers to adapt. Keep it true: an instance that
turns on Sentry's personal data, or an email provider's tracking, says so.
