# Adapting Flashlights

This page is for organizers setting Flashlights up for their own community.
Most of what makes an instance yours is configuration: settings for whoever
runs the deployment, and per-edition settings you change in the portal.
Neither needs a code repository. A community that needs more than that adds
a small Django app of its own, and the core stays untouched.

## What you can change without code

| What | Where you change it | Notes |
|---|---|---|
| Name and short name | Environment | The name is in page titles, share cards and email subjects; the short name is in the navigation bar |
| Accent colour | Environment | One of five presets, or your own colour |
| Logo, share image, favicon | Environment, as URLs | See the next section |
| Help and terms links | Environment | Where the help links and the terms of service link point |
| Sender address | Environment | Who the portal's email comes from |
| Modules you don't use | Environment, as feature switches | Turn off volunteering, sponsorship or the public stats pages if you run none of them |
| Each edition's format, venue, chat, reply-to address and links | The edition form in the portal | Code of conduct, sponsorship prospectus, donation and schedule links are per edition too; a link left empty is not shown |
| Speakers, call for proposals and ticketing | The portal, per edition | The speaker portal is switched on per edition; ticketing is set up on the edition's Tickets page |
| Who can do what | Teams in the portal | Organizers get their access through a team, not as superusers |
| Terms of service and acceptable use policy | The policy templates in these docs | Adapt them, publish your own versions and point the terms link at yours |

The [environment reference](../developer/environment.md) lists every
setting and its default. After changing one, the app has to restart before
it reads the new value. What you change in the portal applies at once.

## Your logo, share image and favicon

1. Host each image somewhere stable that serves it over HTTPS: your
   community website, a CDN, or a public file in a GitHub repository.
2. Put each image's full URL, starting with `https://`, in its setting
   (`SITE_LOGO`, `SITE_OG_IMAGE`, `SITE_FAVICON`), then restart.
3. Leave a setting empty to go without: the navigation bar then shows the
   name alone, and the favicon and share card are drawn from the name and
   the accent colour.

To change an image later, replace the file at the same URL, or point the
setting at a new URL and restart. Browsers may show the old image for a
while after a same-URL replacement, so a new URL shows the change sooner.
If the image's host goes down, the image shows as broken until it is back:
Flashlights falls back to its own only when the setting is empty.

## When configuration is not enough

Ask first whether another community would want the same thing. If so, it
belongs in the core: open an issue describing the need, and it may arrive
as a new setting in a later release. If it is yours alone, build it as a
Django app on the core image; [Community apps](../developer/community_apps.md)
says how, and which parts of the core the app may rely on.

## Replacing a page, an email or a static file

Your app can replace any template or static file the core ships, without
touching the core. Put a file at the same path inside your app:

| To replace | Put the file at |
|---|---|
| The landing page (`templates/portal/index.html` in the core) | `your_app/templates/portal/index.html` |
| The speaker invitation email body | `your_app/templates/emails/speakers/invitation.md` |
| The portal stylesheet (`portal/static/css/portal.css` in the core) | `your_app/static/css/portal.css` |

The core looks in your app first because `EXTRA_APPS` puts your app ahead
of its own, for templates and static files alike.

Start from the core's file at the version your image is built from, and
change only what you must. A replaced file is a copy: when a core release
changes the original, your copy keeps the old version and nothing warns
you. So before each upgrade, compare your copies with the new release's
files. Prefer the smaller tools where they exist: a setting, a template
block you extend, or a signal. If the one you need is missing, open an
issue; it is the kind of change the core takes.

## Documenting your customizations

The core's docs are published per release, at
`https://mariatta.github.io/flashlights/X.Y.Z/`, and an instance's help
links go to the version matching its image unless `DOCS_URL` says
otherwise. A community that only configures needs no docs of its own.

A community with an app of its own documents what is its own, in its own
repository next to the app, published wherever it likes: its features,
every screen it replaced, and its deployment runbook. A replaced template
changes a page the core guide describes, so that page's guide is wrong for
your users and yours has to cover it. For everything else, link to the
core docs at your pinned version, `https://mariatta.github.io/flashlights/0.1.0/user/volunteer/`
say, never to `latest/`, which moves with each release. Point `DOCS_URL`
at your docs, and link to the core's from there; the core never links to
a community's docs.

## Keeping up to date

Watch the core's releases on GitHub. Before upgrading, read the changelog
entries since your current version, especially anything marked breaking or
any migration that cannot be reversed. Then change the image tag (or, with
an app of your own, the `FROM` line of your `Dockerfile`) and deploy. The
release step runs the migrations before the new version serves. An
instance with no `DOCS_URL` has help links that follow the image on their
own; a community with docs of its own moves the links in them to the new
version's core docs by hand.

Rolling back is the same change pointed at the previous tag, as long as no
release in between has a migration that cannot be reversed.
