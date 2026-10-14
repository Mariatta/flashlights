# Organisers

Organisers run the event from the **Organize** hub: the dashboard, the
volunteer applications, the teams, the editions, the sponsors, the
speaker programme and the maintenance pages. Staff accounts see it; a
superuser also sees the admin area and can start the next edition.

## Onboarding a new organiser

1. They create an account and verify it.
2. An existing organiser opens the admin area, finds their account and
   marks it as staff. A superuser flag is for the one or two people who
   look after the instance itself.
3. They sign in again and find Organize in the navigation.

## What the dashboard shows

The top line is this edition's numbers: onboarded volunteers, sponsorship
and donations against their goals, attendees when a ticketing system is
connected. Below it, **Needs attention** lists what is waiting on someone:
applications to review, teams without a lead, sponsors not yet invoiced.
Quick actions take you to the lists.

## Who can do what

Access in the portal comes from teams, not from being marked as staff.
Every team carries two sets of permissions, one for its members and one
its leads hold on top, and a person holds whatever the teams they are on
grant them for the current edition. When the edition changes, so do the
grants: last year's team grants nothing this year.

To give someone access, put them on the right team: review their volunteer
application and assign the team, or add them to it from the team's page.
To see what a team grants, open the team; to see what a person holds and
where each grant comes from, open their volunteer profile.

The usual teams start from a preset when they are created (Organizers,
Volunteer coordination, Sponsorship, Program, Proposal reviewers, Speaker
liaisons, Recordings) and
their sets can be adjusted afterwards on the team's edit form. Superusers
bypass all of this, and the Infra maintainers group, which outlives
editions, is managed in the Django admin.

## Editions

Each year's event is an edition. The edition form carries the dates, the
links (Code of Conduct, sponsors, donations, schedule), the goals, and the
switches for what is on this year: taking volunteer applications, taking
sponsors, taking donations, the speaker portal. Starting the next edition
copies the structure forward and leaves the people to re-apply.

### Planning the next edition

One edition is active: it is what the public sees, and its teams decide who
can do what. The next edition can be started at any time while it does not
exist yet; leave "Activate this edition now" unticked and the current one
stays active.

While it waits, the program pages (sessions, presenters, invitations,
proposals to review, rooms, the schedule) can work on it. Choose it under
"Program for" at the top of the Organize rail; a note there reminds you that
the public site still shows the active edition. The choice is yours alone
and lasts until you sign out. Access does not change: whoever runs the
program this year can plan the next one. Volunteering, sponsorship, stats
and the public proposal form stay on the active edition.

Speakers invited to the next edition have their speaker pages straight
away. When it is time, make the next edition active from its edit page.

### Where and how it happens

Three choices on the edition form shape the speaker portal and what people
are asked for. Each is per edition, so a community that meets in a room one
year and online the next changes nothing but the form.

- **Format**: in person, online or hybrid. In person, sessions are live and
  the portal leaves out what only an online event needs: pre-recorded
  delivery, premieres, the tech check and its booking gate, the speaker's
  upload before the event. Hybrid keeps everything and each session says
  whether it is live or pre-recorded. The **venue** goes with it, picked
  from the Venues page, and is printed on the landing page, the public
  program, the calendar feeds and the schedule emails.
- **Recordings**: none, the team records, or speakers pre-record. With the
  team recording, the team uploads each session's recording after the event
  and the post-production board follows it through transcript, translation
  and publishing; speakers get a line to review their recording. With none,
  there are no files, no video fields and no post-production. Speakers
  pre-recording is the online pipeline, and is not offered in person.
- **Community chat**: Discord, another platform (with a name and an invite
  link), or none. Only a Discord edition asks speakers and volunteers for a
  Discord username and seeds the Discord checklist lines; another platform
  gets a "join the chat" line with its link; none asks nothing.

The default checklist templates are seeded to match, so a new edition
starts with the right lines rather than a list to prune.

### Venues

**Venues** in the Organize rail holds the places your events happen at:
a building such as a convention center, or one room with an address.
Each is added once (name, address, a map or website link, notes for the
team) and reused by every edition, so a community returning to the same
building names it once. An edition picks its venue on its edit page.

The moment an edition picks a venue it has no room at, one room named
after the venue is made, so the place can be scheduled right away: a
meetup's single room, or a conference's first lane to rename and add to.
Starting the next edition carries the previous one's active rooms along,
with their venues. A venue an event or a room still uses cannot be
deleted.

### One event a year, or a series of dates

The edition form first asks what kind of event this is, and the answer
decides which dates it asks for. An edition always has at least one date,
so the schedule editor never offers a whole year of days.

- **One event a year**, a conference or a summit: the **event date** and,
  when it runs over several days, the **last day**. The schedule editor
  offers every day of that run.
- **A series of separate dates**, such as a chapter running a year of
  meetups as one edition: the **event dates**, one row each with a date
  picker and an optional label ("February workshop"), added one at a
  time with **Add a date** and dropped with **Remove**. The schedule
  editor offers only those days, the landing page shows the next one,
  and the edition's span runs from the first to the last. Dates can be
  added or changed any time, so a chapter lists what it knows and comes
  back.

Each date can have several rooms, as a conference day can. A room is there
on every date unless it is tied to some of them on its edit page: a meetup
that moves between venues ties each venue's rooms to the nights it hosts,
so other nights do not show them as empty columns.
