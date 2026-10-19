# Environment reference

Every environment variable Flashlights reads, with its default. An instance
is the container image plus these variables; the same set goes to every
process (web, the workers, the scheduler, the release step).
[Deployment](deployment.md) says how to run the processes and what each
host does with the variables; this page is the list.

**Required** means the boot stops without it in production, naming every
missing variable at once (`portal/boot.py`). Where two names are given, any
one of them is enough. With `DEBUG` on, or under the test suite, only
`SECRET_KEY` is checked. Everything else is optional and has the default
shown.

Switches (`DEBUG`, `VOLUNTEERING_ENABLED`, `USE_OBJECT_STORAGE` and the
like) read `0`, `false`, `no` and `off` as off, in any case; any other value
is on.

Change a variable, then restart every process: settings are read once, at
boot.

## Django and the boot

| Variable | Required | Default | What it is |
|---|---|---|---|
| `SECRET_KEY` | Always | none | Django's secret key; any long random string |
| `DJANGO_ALLOWED_HOSTS` | Yes | none | The hostnames the portal answers on, comma-separated |
| `DEBUG` | No | off | Django's debug mode, for local development only. Leave it unset or off in production |
| `BOOT_CHECK` | No | on | `0` turns the required-variable check off, for a one-off shell on a half-configured environment |
| `PORT` | No | `8000` | The port the `web` process serves on; managed hosts set it |
| `SESSION_COOKIE_NAME` | No | `flashlights_sessionid` | The session cookie's name. Browsers scope cookies by host, not port, so two Django apps on one host need different names |
| `CSRF_COOKIE_NAME` | No | `flashlights_csrftoken` | The CSRF cookie's name, for the same reason |
| `PORTAL_LOG_LEVEL` | No | `INFO` | The level of the apps' own log lines |
| `SENTRY_SDK_DSN` | No | none | Sends errors to Sentry when set. Each event is tagged with the kind of process it came from |
| `SENTRY_SEND_DEFAULT_PII` | No | off | Adds the signed-in person's details, their IP address, request headers and cookies to each Sentry event. Turn it on only when the instance's privacy notice says so ([Third-party code and services](third_party.md)) |

## Database, broker and encryption

| Variable | Required | Default | What it is |
|---|---|---|---|
| `DATABASE_URL` | Yes | none | The Postgres connection URL |
| `SQL_ENGINE`, `SQL_DATABASE`, `SQL_USER`, `SQL_PASSWORD`, `SQL_HOST`, `SQL_PORT` | No | `postgresql`, `postgres`, `postgres`, `password`, `localhost`, `5432` | The connection in parts, read only when `DATABASE_URL` is unset; for local development |
| `CELERY_BROKER_URL` or `REDIS_URL` | Yes | none | The Redis URL the workers and the scheduler share. Managed hosts inject `REDIS_URL` with a Redis add-on; `CELERY_BROKER_URL` wins when both are set |
| `FERNET_KEY` or `FERNET_KEYS` | Yes | derived from `SECRET_KEY` in development | The key for fields encrypted at rest (ticketing API tokens, webhook secrets). `FERNET_KEYS` is a comma-separated list for rotation: the first key encrypts, every key decrypts. Deployment, "One-time configuration", has the steps |

## Email

Set either `EMAIL_URL` or the `DJANGO_EMAIL_*` variables. With neither,
email prints to the console, which only development allows.

| Variable | Required | Default | What it is |
|---|---|---|---|
| `EMAIL_URL` or `DJANGO_EMAIL_HOST` | Yes | none | The SMTP server. `EMAIL_URL` is the whole connection in one variable, `smtp://user:password@host:port/?tls=true`; `smtps://` means SSL. Without a port it is 587 with TLS, 465 with SSL, 25 otherwise. `EMAIL_URL` wins when both are set |
| `DJANGO_DEFAULT_FROM_EMAIL` | Yes | `<short name> <noreply@localhost>` | The address the portal's email comes from. Keep it on a domain you send from (SPF and DKIM); replies go to each edition's reply-to address |
| `DJANGO_EMAIL_PORT` | No | 25 | The SMTP port, with `DJANGO_EMAIL_HOST` |
| `DJANGO_EMAIL_HOST_USER` | No | none | The SMTP user, with `DJANGO_EMAIL_HOST` |
| `DJANGO_EMAIL_HOST_PASSWORD` | No | none | The SMTP password, with `DJANGO_EMAIL_HOST` |
| `DJANGO_EMAIL_USE_TLS` | No | off | STARTTLS, with `DJANGO_EMAIL_HOST` |
| `DJANGO_EMAIL_TIMEOUT` | No | 30 | Seconds a connection to the mail server may wait before the task gives up |
| `EMAIL_RECORD_RETENTION_DAYS` | No | 365 | How long the record of a sent email outlives its edition; a nightly task deletes older ones |

## Object storage

Uploads (images, sponsor logos) go to an S3-compatible bucket from any
provider: DigitalOcean Spaces, AWS S3, Cloudflare R2, Backblaze B2, MinIO.

| Variable | Required | Default | What it is |
|---|---|---|---|
| `USE_OBJECT_STORAGE` | No | off | Turns the bucket on; off, files stay on local disk (development only). `USE_SPACES` is the upstream name of the same switch and still works |
| `AWS_ACCESS_KEY_ID` | Yes | none | The access key, through the S3 API. It must reach the media bucket too, when there is one |
| `AWS_SECRET_ACCESS_KEY` | Yes | none | The secret key |
| `AWS_STORAGE_BUCKET_NAME` | Yes | none | The public-read bucket for uploads |
| `AWS_S3_ENDPOINT_URL` | Yes | none | The provider's endpoint |
| `AWS_S3_REGION_NAME` | No | none | The region; the media bucket falls back to it |

## Speaker media

Speakers' videos and files go to a second, **private** bucket. Deployment,
"Speaker media bucket" and "The media worker", has its lifecycle and CORS
rules and the worker setup.

| Variable | Required | Default | What it is |
|---|---|---|---|
| `SPEAKER_MEDIA_BUCKET` | No | none | The private bucket. Empty, speaker uploads are off |
| `SPEAKER_MEDIA_PREFIX` | No | `speaker-media/` | The folder inside the bucket |
| `SPEAKER_MEDIA_ENDPOINT_URL` | No | `AWS_S3_ENDPOINT_URL` | The bucket's regional host, never a bucket's own host |
| `SPEAKER_MEDIA_REGION` | No | `AWS_S3_REGION_NAME`, else `us-east-1` | The bucket's region |
| `SPEAKER_MEDIA_MAX_BYTES` | No | 16 GiB | The largest file a speaker may upload |
| `SPEAKER_MEDIA_PART_SIZE` | No | 64 MiB | The size of each part of an upload |
| `SPEAKER_MEDIA_URL_TTL` | No | 3600 | Seconds a download or upload link stays valid |
| `SPEAKER_MEDIA_UPLOAD_TTL_HOURS` | No | 48 | Hours before an unfinished upload is abandoned |
| `SPEAKER_MEDIA_BULK_URL_TTL` | No | 43200 | Seconds the links in a bulk download stay valid |
| `SPEAKER_MEDIA_ZIP_MAX_BYTES` | No | 1 GiB | The largest bulk download offered as one zip |
| `SPEAKER_TRANSCRIBE_ENGINE` | No | none | `local` turns on machine transcription with Whisper in the media worker; needs the full image flavour. Empty, the per-edition switch cannot turn it on |
| `SPEAKER_TRANSCRIBE_MODEL` | No | `small` | The Whisper model baked into the image |
| `SPEAKER_TRANSCRIBE_MODEL_DIR` | No | `/opt/whisper` | Where the image keeps the models |
| `SPEAKER_TRANSCRIBE_STALE_HOURS` | No | 12 | Hours before a queued media job is marked as failed |

## Workers

| Variable | Required | Default | What it is |
|---|---|---|---|
| `CELERY_WORKER_CONCURRENCY` | No | 2 | Processes per worker |
| `CELERY_WORKER_QUEUES` | No | `celery,media` | The queues `bin/worker` serves; `celery` when a separate media worker runs |
| `CELERY_EMBED_BEAT` | No | on | Runs the scheduler inside `bin/worker`. `0` on every worker when the scheduler runs as its own `worker-beat` process, so it runs exactly once |
| `CELERY_LOG_LEVEL` | No | `info` | The worker's own log level |

## Identity

What the instance is called and how it looks. The keys mirror the Popular
theme's, so a community sets the same values for its public site.

| Variable | Required | Default | What it is |
|---|---|---|---|
| `SITE_TITLE` | No | `Flashlights` | The community or event name: page titles, share cards, email subjects |
| `SITE_SHORT_NAME` | No | the title | The name in the navigation bar and the email subject prefix |
| `SITE_DESCRIPTION` | No | "*title*: the organisers' portal" | The description on share cards |
| `SITE_LOGO` | No | none | The full `https://` URL of a logo shown beside the name in the navigation bar. Empty, the bar shows the name alone |
| `SITE_FAVICON` | No | generated | The full URL of the favicon. Empty, one is drawn from the title and the accent colour |
| `SITE_OG_IMAGE` | No | generated | The full URL of the share image. Empty, a card is drawn from the title and the accent colour |
| `BRAND_PRESET` | No | `beam` | The accent colour: `beam`, `teal`, `copper`, `indigo` or `raspberry`. Any other value stops the boot |
| `BRAND_PRIMARY` | No | none | A custom `#rrggbb` accent in place of the preset; the ink on it and its hover and press shades are derived |
| `DOCS_URL` | No | the core docs for this version | Where the help links point: your community's own docs when it has some ([Adapting Flashlights](../user/adapting.md), "Documenting your customizations"), else `https://mariatta.github.io/flashlights/X.Y.Z/` for the image's version |
| `TERMS_URL` | No | none | The terms of service link; left out when unset |

## Features and contacts

| Variable | Required | Default | What it is |
|---|---|---|---|
| `VOLUNTEERING_ENABLED` | No | on | Off, the volunteer hub, applications and teams are gone and their pages answer 404 |
| `SPONSORSHIP_ENABLED` | No | on | Off, sponsors, tiers, donations and their stats are gone |
| `STATS_PUBLIC` | No | on | Off, the public stats, year comparison and JSON feed pages are gone |
| `SPONSORSHIP_EMAIL` | No | none | The organisers' sponsorship address; receives the contract request (the sponsor never does) |
| `ACCOUNTING_EMAIL` | No | none | Who issues invoices; also receives the contract request. With neither set, the request is not sent |
| `GDRIVE_FOLDER_ID` | No | none | A shared Google Drive folder linked from the volunteer onboarding emails; the link is left out when unset |
| `UNVERIFIED_ACCOUNT_RETENTION_DAYS` | No | 7 | Days before an account whose email address was never verified is deleted; the verification email quotes it |
| `EXTRA_APPS` | No | none | Django apps a community adds to the core, comma-separated. [Community apps](community_apps.md) has the contract |

Everything else about an edition, its format, venue, chat, reply-to
address, ticketing and call for proposals, is set in the portal, not the
environment, and changes without a restart.

## Build arguments

Read when the image is built, not when it runs.

| Argument | Default | What it is |
|---|---|---|
| `WHISPER_MODEL` | none | Bakes a Whisper model into the image for machine transcription (the full flavour), such as `small` |
| `USER_ID`, `GROUP_ID` | 1000 in `compose.yml` | The ids of the user the development image runs as, so files it writes in the mounted checkout are yours |
