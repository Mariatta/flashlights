# Tiny Little Flashlights

Flashlights is the back-of-house portal for a volunteer-run event or
meetup: volunteers, speakers and their checklists, sponsors, the schedule,
and the files that go with them, in one place instead of a dozen
spreadsheets.

It is derived from the [PyLadiesCon portal](https://github.com/pyladies/pyladiescon-portal)
and keeps pulling improvements from it. One instance serves one community;
each year's event is an edition inside it. What an instance is called, its
colour, its links and which features it runs are configuration, so the
same software serves a three-day online conference and a monthly meetup.
The name is a nod to a Darren Hayes song.

## Where to start

- **Organisers**: the [User Guide](user/get_started.md) says what each
  part of the portal does and which parts a small event can skip.
- **Developers**: the [Setup Guide](developer/setup.md) gets a local
  instance running with sample data in a few commands; the
  [Design System](developer/design.md) page explains the look.
- **Hosting**: [Deployment](developer/deployment.md) is the boot contract:
  the services an instance needs and the variables that configure it;
  the [environment reference](developer/environment.md) lists every one.
- **Your own community**: [Adapting Flashlights](user/adapting.md) is
  what you can change without code, and what to do when that is not
  enough.
- **Your own code**: [Community apps](developer/community_apps.md) is how
  a community adds a Django app to the core image, and which parts of the
  core it may rely on.

## Nothing loads from anywhere else

Every page is served by the instance itself: the fonts, the icons, the
charts and every script. There are no analytics, no advertising and no
third-party cookies, and a third-party service is used only when it is
absolutely needed and no adequate open-source, self-hosted option exists.
[Third-party code and services](developer/third_party.md) lists what is
vendored, how its updates arrive, and the services an instance talks to
on the server side.

## Licence and contributions

Flashlights is free software under the GNU AGPL version 3, with an
additional permission to run a modified copy for your own organisation's
events without publishing the changes. It is published for use and study
and does not take code contributions; bug reports, ideas and reports of what
confused you are welcome as issues. See
[Working on the code](developer/contributing.md).

- Repository: <https://github.com/mariatta/flashlights>
- Issues: <https://github.com/mariatta/flashlights/issues>
