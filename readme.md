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
| `SITE_LOGO`, `SITE_FAVICON`, `SITE_OG_IMAGE` | Absolute URLs; a generated favicon stands in when unset | unset |
| `BRAND_PRESET` | `teal`, `copper`, `indigo` or `raspberry` | `teal` |
| `BRAND_PRIMARY` | A custom `#rrggbb` primary; hover and active shades are derived; refused below 3:1 contrast on white | unset |
| `DOCS_URL`, `TERMS_URL` | Documentation and terms of service links; left out when unset | unset |

The Code of Conduct link comes from the active edition's record.

## Local Dev setup

Go to [the Dev setup documentation page](docs/developer/setup.md).
