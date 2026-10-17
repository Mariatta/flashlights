# Community apps

Flashlights is one generic core, released as a container image. Most
communities deploy that image as it is: their data is in their database,
their look is in environment settings, and they need no repository. A
community that needs code the core should not carry, a page of its own, a
report, a model, adds one small Django app that plugs into the core image.
The core never carries a community's code.

This page is for the developer writing such an app. It says how the app is
loaded, what it can do, and which parts of the core it may rely on.

## How an app is loaded

`EXTRA_APPS` is a comma-separated list of Django apps, each the dotted path
of a package the image can import. Empty or unset, the core runs bare. For
each app named, the core:

- puts it in `INSTALLED_APPS` **ahead of its own apps**, so the app's
  models, admin, management commands, signals and `AppConfig.ready()`
  work as in any Django project;
- searches the app's `templates/` folder **before the core's own**, so a
  file at the same path replaces a core template;
- serves the app's `static/` files through the same static files pipeline,
  collected at image build like the core's;
- includes the app's `urls` module, when it has one, under a prefix.

The URL prefix is the app's `prefix` attribute in its `urls` module
(`prefix = "summit/"`), or, when the module sets none, the last part of the
app's module path with hyphens for underscores (`flashlights_summit` is
served under `/flashlights-summit/`). The module's `app_name` becomes the
namespace, so the app's templates reverse `{% url 'summit:schedule' %}` as
usual. A prefix must not be one the core uses (`speakers/`, `events/`,
`accounts/`, `api/`, `admin/` and the rest in `portal/urls.py`).

A misspelled entry fails the boot by name:

```
EXTRA_APPS names 'flashlights_sumit', which is not an importable package.
```

## The community's repository

A plain repository, not a fork of the core, holding the app, its tests, a
`Dockerfile` and the deployment. The `Dockerfile` is a few lines:

```dockerfile
FROM ghcr.io/mariatta/flashlights:0.4.0
COPY . /community
RUN pip install /community
ENV EXTRA_APPS=flashlights_summit
RUN BOOT_CHECK=0 SECRET_KEY=build-only DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgres://localhost:5432/db \
    python manage.py collectstatic --noinput --clear
```

The second `collectstatic` adds the app's static files to the image, with
the placeholder values the core's own build uses. Everything else about
running the image is the core's [boot contract](deployment.md): the same
processes, the same variables, the same hosts. The community's name,
colours, logo and email settings stay environment variables, as for any
deployment. Upgrading the core is a one-line change to the `FROM` tag in
a pull request, and the repository's CI should build the image, run the
app's tests against the new core and load the community's demo data into
a fresh database, so a release that breaks the app fails there first.

## Replacing a page, an email or a static file

Put a file at the same path inside the app:

| To replace | Put the file at |
|---|---|
| The landing page (`templates/portal/index.html` in the core) | `flashlights_summit/templates/portal/index.html` |
| The speaker invitation email body | `flashlights_summit/templates/emails/speakers/invitation.md` |
| The stylesheet | `flashlights_summit/static/styles.css` |

Start from the core's file at the version the image is built from and
change only what you must. A replaced file is a copy: when a core release
changes the original, the copy keeps the old version and nothing warns
you. Before each upgrade, compare your copies with the new release's
files. Prefer the smaller tools where they exist: a setting, a template
block you extend, a signal. If the block or setting you need is missing,
open an issue describing the need; a change that another community could
use belongs in the core.

## Where a change goes

New work goes to the core by default. A community repository gets only
code no other community could use.

| The change | Where |
|---|---|
| Anything another community could use, even when one community asked for it | The core, generic and configurable |
| A community's data, name, colours, links | Its deployment's database and settings, never a repository |
| A page, report or model only one community uses | The community app |
| A community-only change to what a core view or form does | An extension point in the core first, then the app uses it |
| A core file edited in a community repository | Never |
| An urgent fix in core code | A core patch release, then deployments bump their tag |
| An urgent fix in community code | The community repository, no core release |

The test for any change: would a meetup group or another conference want
it? If yes, it is core.

## Extension points

An app can add anything on its own: pages, models, reports, commands,
emails. Changing what a core view or form does goes through a deliberate
extension point, added to the core the first time a community needs one.
The shapes the core will use, in the order they are likely to arrive:

- **Swappable classes as settings**, the way Django swaps `EMAIL_BACKEND`:
  a setting names the form or class to use in place of the core's.
- **Signals** at the moments communities care about, such as a confirmed
  registration, an accepted proposal or a published edition.
- **Named template blocks** in the core's templates, so an app extends a
  page instead of copying it.
- **A navigation hook**, so an app's pages appear in the menus without
  replacing the base template.

None of these exists yet. Ask for the one you need with an issue that
says what the app would do with it.

## Public API

A community app depends on parts of the core, so those parts are a
contract. Until 1.0 every upgrade deserves a real test pass, not only a
tag bump; from 1.0 the changelog marks any change to these as breaking:

- the environment variables, as the
  [environment reference](environment.md) lists them;
- `EXTRA_APPS`: that the apps go first in `INSTALLED_APPS`, that their
  `templates/` and `static/` win over the core's, and how their `urls`
  module is included (the `prefix` attribute, the default prefix, the
  `app_name` namespace);
- the template names and paths an app may replace, and, once they exist,
  the named blocks inside them;
- the swappable settings and the interfaces their classes implement, and
  the signals and their arguments, once they exist;
- `manage.py load_preset <directory>` and what a preset's `seed.py` may
  rely on: the models below and the management commands;
- the models a community app may point a foreign key at: `Conference`,
  `EventDate`, `Venue` and `Room`; `Team` and
  `VolunteerProfile`; `Presenter`, `Session`, `Proposal` and `ChecklistItem`;
  `SponsorshipProfile` and `SponsorshipTier`; `PortalProfile` and `Handle`.
  Point at them, never alter them; a field a community needs on a core
  model is a core change;
- the management commands.

Private, and free to change in any release: everything else, including
view classes, form classes, template context names, URL names other than
the public pages', and the internal modules.
