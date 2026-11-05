# Deployment

Flashlights is one container image with one boot contract, and it runs the
same way on every host. This guide has three parts: the contract, which
every host fulfils; running an instance, which is the same whoever hosts
it; and one worked example per host, Heroku and its compatibles, Azure,
Cabotage and a plain server, with that host's own steps and quirks.

## The boot contract

An instance is the container image plus environment variables, started the
same way on every host: the release step runs migrations,
`web` serves on `$PORT`, `worker` runs the queue. Four services are
required, Postgres, Redis, an S3-compatible bucket and an SMTP server, from
any provider.

In production (`DEBUG` off) the boot stops at once, naming every missing
variable, when one of these is unset:

| Variable | What it is |
|---|---|
| `SECRET_KEY` | Django's secret key; required in every environment |
| `DJANGO_ALLOWED_HOSTS` | The hostnames the portal answers on, comma-separated |
| `DATABASE_URL` | The Postgres connection URL |
| `CELERY_BROKER_URL` or `REDIS_URL` | The Redis URL the worker and beat share; managed hosts inject `REDIS_URL` |
| `FERNET_KEY` or `FERNET_KEYS` | The key for fields encrypted at rest (see One-time configuration) |
| `DJANGO_EMAIL_HOST` or `EMAIL_URL` | The SMTP server. `EMAIL_URL` is one variable, `smtp://user:password@host:port/?tls=true`; `smtps://` means SSL |
| `DJANGO_DEFAULT_FROM_EMAIL` | The address the portal's email comes from. Keep it on a domain you send from (SPF and DKIM); replies go to each edition's reply-to address, set on the edition form, so a team with only a Google Group can still receive them |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL` | The bucket, through the S3 API: DigitalOcean Spaces, AWS S3, Cloudflare R2, Backblaze B2 or MinIO. `USE_OBJECT_STORAGE=true` turns it on; the upstream name `USE_SPACES` still works |

Everything else has a default; the [environment reference](environment.md)
lists every variable. With `DEBUG` on, and under the test suite,
nothing but `SECRET_KEY` is checked: email prints to the console and files
stay on disk. `BOOT_CHECK=0` turns the check off for a one-off shell on a
half-configured environment.

`EXTRA_APPS` is the one optional variable that changes what the image
runs: the Django apps a community adds, built into an image of its own
from the core's. [Community apps](community_apps.md) has the contract.

**The health route.** `GET /_health/` (or `/_health`) answers `200 ok` as
plain text. It is answered before Django checks the `Host` header and runs
no query, so a host can probe the web process at the pod's own address,
with no hostname configured, and a database that blinks does not get the
web process restarted. Point every liveness and readiness probe, proxy
health check and uptime monitor at it; it is the only path that skips the
host check. It says the process answers, nothing more: whether the
database and the workers are well is shown on the maintenance pages.
gunicorn keeps the probes out of its access log.

### Processes and formation

The `Procfile` names the processes; every host runs the same image.

| Process | What it does | When |
|---|---|---|
| `release` | Creates the cache table and runs migrations | Before each new version serves |
| `web` | gunicorn on `$PORT` | Always |
| `worker` | `bin/worker`: serves every queue and runs beat embedded | Always; the minimum formation is web plus one worker |
| `worker-media` | Serves the media queue alone (probes, transcription), one job at a time | Optional: when media jobs should not hold up emails and reminders |
| `worker-beat` | The scheduler on its own | Optional: when there is more than one worker, with `CELERY_EMBED_BEAT=0` on every worker so beat runs once |

`bin/worker` reads two variables: `CELERY_WORKER_QUEUES` (default
`celery,media`; set `celery` when a media worker exists) and
`CELERY_EMBED_BEAT` (default on). `compose.yml` runs the minimum formation.

Whatever the host, the scheduler must run exactly once: either embedded in
the one `worker`, or as one `worker-beat` replica with `CELERY_EMBED_BEAT=0`
on every worker. Two schedulers dispatch every periodic task twice. If a
scheduled task never fires, check that before anything else: in the Django
admin, under *Periodic tasks*, a task whose *Last run at* is empty has never
been dispatched, which almost always means no scheduler is running.

### Image flavours

The image comes in two flavours. **Slim**, the default build, has no
transcription library and no model; it is what most instances need and
about 500 MB lighter. **Full** adds machine transcription: build with
`--build-arg WHISPER_MODEL=small` (or another faster-whisper model) and
the library and model go into the image, under `/opt/whisper`, in a layer
before the code, so a code-only build reuses it. A host that cannot pass
build arguments deploys a prebuilt full image by tag,
`ghcr.io/mariatta/flashlights:X.Y.Z-full` ([Releasing](releasing.md)
lists the images each release publishes). The media worker
section below says what to set once the full image runs.

### The lite profile

Three switches turn off what a community does not run.
Off, a feature's pages answer 404 and its navigation, dashboard, landing
and stats entries disappear.

| Variable | Default | Off means |
|---|---|---|
| `VOLUNTEERING_ENABLED` | `true` | No Volunteer hub, applications or teams |
| `SPONSORSHIP_ENABLED` | `true` | No sponsors, tiers, donations or their stats |
| `STATS_PUBLIC` | `true` | No public stats, comparison or JSON feed pages |

The speaker portal is switched per edition, on the edition form. A
community that runs none of volunteering, sponsorship and the speaker
portal still gets accounts, editions, the schedule by hand and the public
site export; its formation is web plus one worker and the slim image.

## Running an instance

Everything in this part is true on every host. Where a host's own screens
or commands differ, the host's example below says so.

### Release step and migrations

The `release` line in the `Procfile` runs before the new version starts
serving. It creates the cache table and runs `python manage.py migrate`
against the instance's database. Every migration file in the version being
deployed is therefore applied to production on the next deploy, without
anyone confirming it.

That gives migrations one rule: **a migration is frozen once it is merged.**

- While a pull request is open, its migration files may be regenerated,
  renamed or squashed freely. Nothing applies them except a developer's own
  database and the CI test run.
- After the pull request is merged, the migration is part of production's
  history. Never edit it in place, delete it or renumber it. Any further
  schema change is a new migration file, even a one-line fix.
- If production ever diverges from the migration files (a column missing,
  a migration recorded as applied that did something else), repair it with a
  new migration that checks before it acts, such as a `RunSQL` with
  `ADD COLUMN IF NOT EXISTS`. `speakers/migrations/0002_repair_invitation_sent_to.py`
  is an example.

Keep pull requests to one migration per app: squash the steps a branch
accumulated into a single regenerated file before asking for review, and
check it with `makemigrations --check` and a `migrate` on a fresh database.

**Preview environments need a database of their own.** Some hosts can
build and deploy every push of an open pull request. A preview that shares
the production database runs the release step against it, so `migrate`
applies code that has not been reviewed and may never merge. A migration
later changed on the branch has already been recorded as applied, Django
skips the merged version, and production ends up with a schema matching
neither the branch nor `main`; an abandoned pull request leaves its tables
behind with nothing describing them. Only the deployed branch should ever
touch the production database. Pull requests are verified by the CI test
run, which builds its own database from the migration files.

### Adding a column during a rolling deploy

The release step runs `migrate` and only then serves the new release, so
there is a window, usually seconds, where the schema is new and the code is
old. A column added as NOT NULL breaks that window: Django backfills the
existing rows with a default and then **drops** it, so the column has no
database default, and a process from the previous release inserts a row
without it. Postgres refuses:

```
null value in column "default_team_name" of relation
"speakers_checklisttemplateitem" violates not-null constraint
```

It clears up on its own once the new release is serving, but it is 500s for
real people in the meantime, and it is avoidable. When adding a NOT NULL
column, give it a **database** default as well as a Python one:

```python
default_team_name = models.CharField(max_length=40, blank=True, db_default="")
```

`db_default` (Django 5) keeps the default in the schema, so the old code can
keep inserting until it is replaced. Keep the ordinary `default` as well:
with only a `db_default`, an unsaved instance holds a sentinel rather than
the value, and anything reading the attribute before the row is saved, a
`clean()` for instance, sees the sentinel.

`tests/speakers/test_deploy_window.py` walks the migration graph for every
column added to a table that already existed and fails if one is NOT NULL
with nothing behind it, so the rule cannot drift as columns are added. A
foreign key is the case where no default exists: add it nullable, backfill
it, and tighten it in a later release.

The same window applies to a column that is later removed: drop it from the
model first, deploy, then delete the column in a follow-up migration.

### Database

The portal needs **PostgreSQL 15 or newer**. The speakers app declares unique
constraints with `nulls_distinct=False` (so a row with a NULL presenter
still counts as a duplicate of another). Django only emits that clause on
Postgres 15+; on an older server it warns with `models.W047` at check time
and creates the constraint without it, which silently allows the duplicates
the constraint exists to prevent. Local development and CI run `postgres:16`
from `compose.yml`; managed Postgres on the hosts below is 16 or 17. The
image ships no `psql`, so `manage.py dbshell` does not work in production;
ask Django instead:

```
python manage.py shell -c "from django.db import connection; print(connection.pg_version)"
```

The number reads as major and minor: `170002` is 17.2.

### Speaker media bucket

Speaker media lives in its own **private** bucket, named by
`SPEAKER_MEDIA_BUCKET`, never the public-read one the image fields use. It
needs a lifecycle rule that aborts incomplete multipart uploads after 7
days (`AbortIncompleteMultipartUpload`): the portal's nightly "Expire
abandoned uploads" task reclaims what it knows about, and the rule reclaims
the rest. The nightly "Expire export zips" task deletes the zip of every
bulk-download export past its expiry. The bucket also needs a CORS rule
allowing `PUT` from the portal's origin with the `ETag` header exposed,
since the browser uploads the parts directly. Bulk download needs `GET` in
the same rule for the browser's folder download, and a second lifecycle
rule that expires the `exports/` prefix after 7 days, since zip bundles are
built there and their links die with the export after twelve hours.

**Endpoint and region.** The media client reads `SPEAKER_MEDIA_ENDPOINT_URL`
and `SPEAKER_MEDIA_REGION`, each falling back to `AWS_S3_ENDPOINT_URL` and
`AWS_S3_REGION_NAME` when unset or blank. Set them to the media bucket's
regional host and region (`https://sfo3.digitaloceanspaces.com` and
`sfo3` on DigitalOcean, say), not a bucket's own host: boto3 puts the
bucket name in the path, so a host that already names another bucket signs
every upload for the wrong one, and the browser's preflight fails with no
`Access-Control-Allow-Origin`. A region that is not the bucket's gives a
signature error. The image storage keeps using the `AWS_*` variables
unchanged. The access key must reach both buckets.

**Read-only key for a post-production lead.** One escape hatch needs no
portal code: a key with read-only access to the media bucket, so one
trusted person can pull an edition with `rclone`. Create it scoped to the
media bucket only with read permission, and hand it over through the
password manager, never by email or chat. Revoke it when the edition's
post-production is done; nothing in the portal records what such a key
fetches.

```sh
rclone config create do-media s3 provider=DigitalOcean \
    endpoint=nyc3.digitaloceanspaces.com \
    access_key_id=<key> secret_access_key=<secret>
rclone sync do-media:flashlights-media/speaker-media/2026 ./flashlights-2026 \
    --progress --transfers 4
```

### The media worker

Media jobs run for minutes at a time: the duration probe measures every
video that lands with `ffprobe`, and machine transcription runs Whisper.
They go on the `media` Celery queue (`CELERY_TASK_ROUTES` in settings).
The minimum formation's `worker` serves that queue along with everything
else; a larger instance runs the `worker-media` process for it instead, so
a half-hour transcription never holds up an invitation email.

- The image installs `ffmpeg`, which brings `ffprobe`.
- A probe that fails records why on the asset ("Length not measured:
  ffprobe is not installed on the worker", for instance), which the file
  rows show, and logs an error; the asset itself stays usable.
- When no process is consuming the media queue, every uploaded video shows
  "Length not checked yet" for good: the probe is queued and nobody takes
  it. The nightly watchdog marks a job queued for over twelve hours as
  failed on the page. After adding `worker-media`, check it is actually
  running (some hosts start a new process at zero replicas; see Cabotage
  below) and set `CELERY_WORKER_QUEUES=celery` on the default worker.

Transcription needs the full image flavour, then:

- set `SPEAKER_TRANSCRIBE_ENGINE=local` (and `SPEAKER_TRANSCRIBE_MODEL`
  to the model that was baked in) on every process, since the web
  process reads the first to offer "Transcribe this"; then switch *Auto
  transcribe* on per edition under Speaker settings for automatic drafts;
- transcription runs entirely in this process; no audio leaves the
  instance's infrastructure, and there is no API key to manage.

**What a second worker process costs.** It is one more container with its
own memory reservation (the Whisper model is what sets it), one more
process to keep running, and one more thing that can sit at zero without
anything failing loudly. It shares the image, so `ffmpeg` and the
`faster-whisper` dependency are in every process's image whether or not
they use them (about 250 MB more image, plus about 500 MB for the Whisper
model layer). Everything else is unchanged: `web`, `worker-beat` and
`release` do not know it exists, and the default `worker` keeps consuming
only its own queue.

The alternative is the minimum formation: one worker consuming both queues
with two child processes. It saves the container, but the whole worker then
needs the model's memory, a transcription and an email share the same
limits, and two slow transcriptions would hold every email until one
finishes. The separate process is the recommended shape once an instance
transcribes; the single worker is right for everyone else, and switching is
a Procfile and settings change, not a code change.

### Email and worker settings

These are read from the environment of every process. All have defaults, so
none is required.

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_EMAIL_TIMEOUT` | 30 | Seconds a connection to the mail server may wait. Applies when `DJANGO_EMAIL_HOST` is set. Without a timeout, a server that accepts the connection and then says nothing holds a worker process for ever. |
| `DJANGO_EMAIL_HOST_PASSWORD` | none | The SMTP password. |
| `CELERY_WORKER_CONCURRENCY` | 2 | Processes per worker. Celery's own default is one per CPU it can see, which in a container is often the node's core count rather than the container's share; a small memory limit then gets a process killed, and the task it held with it. `worker-media` sets its own on the command line. |
| `PORTAL_LOG_LEVEL` | `INFO` | Level for the apps' own log lines. |

Workers hand each process one task at a time (`CELERY_WORKER_PREFETCH_MULTIPLIER`
is 1), so a long task does not leave others reserved behind it while another
process sits idle. The broker connection is bounded and kept alive
(`CELERY_BROKER_TRANSPORT_OPTIONS`).

**What the email tasks do when something goes wrong.** The tasks that send one
email to one person (the invitation, the acceptance and added-to-session
emails, and the approved and rejected proposal replies) are acknowledged when
they finish, not when they start, so a worker that is killed or restarted
while holding one gives it back to the queue. They retry a mail server that is
down or slow (four times, with growing waits), and give up at once on an
address the server refuses or a login it rejects. Each has a time limit, so a
stalled connection cannot hold a process. A task that runs twice (a worker
that dies after the mail server accepted the message) checks first whether the
send is already on record and does not mail the person again. A worker logs
`Worker ready: <name> process=<kind> email_code=<fingerprint>` each time it
starts, so a worker that restarts every few minutes shows as a run of those
lines, and each one says which code it came up with. Sentry events carry a
`process` tag (`web`, `worker`, `worker-media` or `beat`) so an error can be
traced to the kind of process it came from. The digests and the notices to the
organizers are not retried, because a retry would send again to people who
already have them.

### Emails queued but never sent

An email is queued by the web process and sent by the `worker` process. The
presenter page calls an invitation **Sent** the moment it is queued, and the
record that the email actually went out (a row under Maintenance > Emails) is
written by the worker. If the worker is killed or restarted while it holds the
task, the task is lost without an error: nothing in Sentry, no failed record,
and the page still says **Sent**.

**Maintenance > Invitations** (maintainers only) finds these. It lists the
active edition's invitations that were marked sent and have no successful
email record for that send, oldest first:

| Email record column | Meaning |
|---|---|
| **No record** | Nothing was recorded. The task was most likely lost. |
| **Failed** | The worker tried and the mail provider refused; the error is shown. |
| **Probably still queued** | Marked sent in the last five minutes. Wait; its button is disabled for now. |

Check a row, then press its **Send again** button. It is one invitation at a
time on purpose: the email goes to a real person and the link in any earlier
email stops working, since each send gets a fresh link and expiry. Press it
once; a second press within five minutes is refused. A row leaves the list
once its email is recorded. If it is still there a few minutes later, the send
is failing again: look in the worker log (below).
Every send from this page is an activity entry on the presenter and the
session ("Sent again from Maintenance") and appears at the bottom of the page.

Limits worth knowing:

- Only invitations that are still waiting are listed. One that was opened,
  accepted, declined or cancelled is not missing anything.
- Only sends made since the portal started recording emails can be checked.
  The page says from when: it is when the migration that created the record
  table was applied, not the age of the oldest surviving record, so a lost
  first send is still found and the nightly prune cannot hide one. If the
  worker kept running older code for a while after that deploy, its sends in
  that window have no record though they were delivered, and are listed.
- If the mail provider accepted a message and the process died before the
  record was saved, the speaker has the email but the page lists it. Sending
  again gives them a second one.

**Check the workers after every deploy.** Every worker reading the default
queue takes tasks, and a task goes to whichever takes it first. A release
can leave an older `worker` container running beside the new one, and then
some emails are sent with the old code: without a record, without the log
lines, with the old behaviour, while the deploy reports success. The top of
**Maintenance > Invitations** lists every worker attached to the broker: its
name, which queue it reads, how long it has been up, and whether it runs the
same email code as the site. The check after a deploy is one default worker,
saying **same as this site**, and one media worker (a worker started with
`-Q celery,media`, as in the minimum formation, counts as both). Red alerts
name the problem: more than one worker reading the default queue, none
reading the default queue, none reading the media queue (thumbnails,
transcription and downloads wait), or a worker whose code the page cannot
confirm. That last one reads one of four ways: **not reported** means the
worker answered that it does not know the command, so it runs code older
than the page and should be removed; **differs** shows a different
fingerprint of the files that decide what an email task does
(`common.workers.email_code_version`); **error** is a worker that knows the
command and failed, with its error; **no answer** is a worker that was
attached but did not reply in time, which may be busy or stuck. The
fingerprint is of the code the process started with, so a changed file
shows the old value until the process restarts.

The page takes about a second longer to load while it waits for answers. If
the broker cannot be reached it says so within a few seconds instead of
hanging: connecting is bounded by `CELERY_BROKER_TRANSPORT_OPTIONS`
(`socket_connect_timeout`, which also bounds a worker's own connect), and the
page gives up after the wait plus a few seconds. The same list is available
from a shell with `celery -A portal inspect ping`.

**Finding out why.** Open the `worker` process's logs on your host, apart
from `web`'s (each example below says where they are), and check it is
running at all. The apps log at INFO to standard output (`PORTAL_LOG_LEVEL`
changes the level). For one invitation the lines are, in order:

```
INFO speakers.services: Invitation 482 for presenter 91 marked sent by 7; email queued on commit
INFO common.tasks: Queued speakers.tasks.send_invitation_email_task as task 3f1c...
INFO speakers.tasks: Invitation email: sending invitation 482 to presenter 91 (task 3f1c...)
INFO speakers.tasks: Invitation email: invitation 482 sent, email record 1042 (task 3f1c...)
```

The task id ties the web log to the worker log; Celery's own `received` and
`succeeded` lines carry the same id. A `received` line with no `succeeded`,
or a `WorkerLostError` or "Worker exited prematurely" line, means the worker
died holding the task: look for restarts and out-of-memory kills of the
`worker` process at that time. No `received` line at all means the task never
arrived: search the web log for `Failed to enqueue Celery task`, which is a
broker (Redis) outage. A failure inside the task logs the traceback and the
invitation id, and goes to Sentry. Addresses are never logged.

Celery starts one child process per CPU it can see, which in a container is
often the node's core count, not the container's share; a small memory limit
then gets a child killed. `CELERY_WORKER_CONCURRENCY` bounds it (default 2);
lower it if restarts coincide with lost emails. The design for tracking
delivery, and the steps not built yet, are in
`docs/architecture/email-delivery.md`.

### One-time configuration

Two things live outside the code and have to be set on a new environment:

**Site domain.** Emailed links (account verification, speaker invitations,
checklist reminders) are built from the domain in Django's sites framework,
which starts as `example.com`. After the first deploy, set it to the
portal's public hostname, either from a shell on the instance:

```sh
python manage.py set_site_domain portal.example.org
```

or in the Django admin under **Sites**. Links are `https://` whenever
`DEBUG` is off.

**`FERNET_KEYS` environment variable.** The speaker portal stores the pretix
API token and webhook secret encrypted at rest and refuses to save them
without a key. Generate one once and keep it with the other deployment
secrets:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The variable is comma-separated so keys can be rotated: the first key
encrypts, every key decrypts. To roll a key, put the new one first, deploy,
re-save the stored secrets from the admin, then drop the old key. A single
`FERNET_KEY` is accepted too. A value stored under a key that is no longer
configured reads as unusable (pretix shows as not configured, and the app
logs it once) rather than breaking every page that loads the settings;
re-entering the secrets in the admin repairs it. Local development and the
test suite derive a key from `SECRET_KEY`, so neither needs the variable.

## Hosts

Every host runs the same image and the same `Procfile`. Each example below
follows the same order: what to create, how the processes map onto the
host, how the release step runs, where the logs are, and the host's own
quirks. Pick one; nothing in the code knows which you chose.

### Heroku and compatible hosts

Heroku, and the hosts that read the same files (Dokku, Render through its
import, and others).

**What to create.** `app.json` and `heroku.yml` describe the instance: the
Dockerfile build (slim flavour), the Postgres and Redis add-ons, the `web`
and `worker` processes, the release command, and every variable with a
description. The Deploy button creates an app from them. What it cannot
provision is the bucket and the mail provider, so the four storage
variables, `EMAIL_URL` and `DJANGO_DEFAULT_FROM_EMAIL` are asked for at
creation, and `FERNET_KEY` is generated by hand (the command is in the
prompt). `DATABASE_URL` and `REDIS_URL` come from the add-ons.

**Processes.** `heroku.yml` runs `web` and `worker`, the minimum
formation, each as a dyno. The host sets `$PORT` and routes to it. To add
`worker-media` or `worker-beat`, add their lines from the `Procfile` to
`heroku.yml`'s `run` section and scale them to one.

**Release step.** `heroku.yml`'s `release` runs the cache table and
migrations before the new dynos take traffic. A failed migration stops the
deploy and the old release keeps serving.

**Health.** Heroku runs no probes; it only checks that `web` binds
`$PORT` in time. Dokku and Render do probe, and an uptime monitor should:
give them `/_health/`.

**Logs.** `heroku logs --tail --dyno worker` (or the host's equivalent)
shows one process's output; all processes share one stream otherwise.

**Quirks.** Check the add-on's Postgres version is 15 or newer (Database,
above). The Key-Value Store add-on requires TLS and presents a self-signed
certificate: its `REDIS_URL` starts with `rediss://`, and for such a URL the
portal connects without verifying the certificate unless the URL carries
its own `ssl_cert_reqs` (Heroku's own guidance for its Redis clients), with
no warning in the worker log. Heroku restarts dynos daily, which the email
tasks tolerate (they are acknowledged on completion). After the first deploy, set the site
domain (One-time configuration) and add your own domain to the app and to
`DJANGO_ALLOWED_HOSTS`.

### Azure Container Apps

**What to create.** `deploy/azure/main.bicep` provisions Postgres Flexible
Server, Azure Cache for Redis and a Container Apps environment from an
image tag. The bucket comes from an S3-compatible provider (Cloudflare R2
or Backblaze B2, say) and is passed in as parameters, since Azure Blob does
not speak the S3 API. `deploy/azure/README.md` has the commands;
`params.example.json` lists the parameters, and the filled-in
`params.json` holds secrets and is ignored by git.

**Processes.** `web` and `worker` are two container apps on the same
image, `web` with ingress on port 8000, which the template also sets as
`$PORT`, `worker` with none. More processes are more container apps with the
`Procfile` line as their command, one replica each.

**Release step.** A manual Container Apps job runs the release command.
Start it after every image change, before scaling the new revision in:
`az containerapp job start -g <group> -n <name>-release`.

**Health.** The template declares startup, readiness and liveness probes
on `web` against `/_health/` on port 8000; a revision takes traffic once
the readiness probe passes, and a replica that stops answering is
replaced. `worker` has no port and no probes.

**Logs.** Each container app has its own log stream in Log Analytics and
under `az containerapp logs show -n <app>`; the worker's lines are under
the worker app, not the web one.

**Quirks.** The release step is not automatic: a deploy that skips the job
serves new code on an old schema. Set the site domain and add the custom
domain to the web app's ingress after the first deploy.

### Cabotage

[Cabotage](https://github.com/cabotage/cabotage-app) is the platform the
portal this project forked from runs on; the `Procfile`'s shape and some of
the operational notes above were learned there.

**What to create.** An application in cabotage pointing at the repository
and branch. Cabotage builds the image itself and passes no build
arguments, so it gets the slim flavour; for transcription, deploy a
prebuilt full image by tag instead. Postgres, Redis, the bucket and SMTP
are external services whose URLs go into the application's configuration.

**Processes.** Each `Procfile` line is a separate deployment with its own
logs and replica count. Cabotage hands `web` a unix socket rather than a
port: `config/gunicorn.conf.py` binds to the socket when the cabotage
socket directory exists and to `$PORT` everywhere else, and writes the
`/tmp/app-initialized` marker cabotage waits for. Process names must
avoid cabotage's reserved names; `beat` is one, which is why the scheduler
is `worker-beat`.

**Release step.** The `release` line runs on every deploy of the branch,
before the other processes are replaced. Deploys happen on every push of
the configured branch.

**Health.** Cabotage probes `web` through its TLS sidecar, every few
seconds, at the application's Health Path, whose default is `/_health/`:
the route the image serves, so leave the default and leave Health Host
empty. A different path, or a host the instance does not answer on, keeps
the pod from ever becoming ready and the deploy times out.

**Logs.** Open the process (`web`, `worker`, `worker-media`,
`worker-beat`) in the application; each has its own log view and events,
where restarts and out-of-memory kills show.

**Quirks.**

- **Keep the project and application names short.** Cabotage names each
  Kubernetes object after the project, the application, a random suffix
  for each, and the process, and Kubernetes refuses a name over 63
  characters. A project called `pyladies-vancouver-flashlights` with an
  application called `flashlights` is one character over for `web`, and
  the deploy fails at "Fetching web Service" with `must be no more than 63
  characters`. Neither name can be changed afterwards. Keep the two names
  together under about 30 characters (`pyladies-vancouver` and
  `flashlights`, say), which leaves room for `worker-media`.
- **A new or renamed process starts at zero replicas.** Cabotage does not
  scale it automatically, and a deploy that adds or renames a `Procfile`
  entry reports success without ever running the new process. After the
  deploy, open the application and scale the new process to the intended
  count, typically 1. A renamed process is a new process from cabotage's
  point of view: scale the new name up and the old name down. This is how
  a freshly added `worker-media` leaves every video at "Length not checked
  yet".
- A release can leave an older worker pod running beside the new one for a
  while, both under the one process; the worker check at the top of
  Maintenance > Invitations shows it.
- Cabotage can deploy every push of an open pull request as a preview that
  shares the application's configuration, database included. Leave that
  off unless the previews get a database of their own (Release step and
  migrations, above).
- A configuration copied from another application may miss a variable;
  the boot check names it at start.

### A plain server

**What to create.** A host with Docker, a Postgres 15 or newer, a Redis,
and the bucket and SMTP from any provider. `compose.yml` is the development
stack and the template: its `web` and `celery` services are the minimum
formation, its `postgres` and `redis` the two services. A production stack
is the same shape with the published image instead of a build, the
`Procfile` commands instead of `runserver`, the variables from the boot
contract in an env file, and a reverse proxy with TLS in front of `web`.

**Processes.** One container per `Procfile` line you run, all from the
same image, with the line as the container's command. `web` serves on
`$PORT` (default 8000); put the proxy in front of it. The proxy must send
`X-Forwarded-Proto: https` (Caddy and nginx's `proxy_set_header` do), and
`web` must not be reachable except through it: the portal trusts that
header, and a request that reaches `web` directly can claim to be secure.

**Release step.** Run the release command yourself before starting the new
containers: `docker compose run --rm web python manage.py createcachetable
&& docker compose run --rm web python manage.py migrate`, or the same two
through whatever starts your containers.

**Health.** Give the proxy's upstream health check, the container's
`healthcheck`, and your uptime monitor `/_health/` on `web`; it needs no
`Host` header.

**Logs.** `docker compose logs -f celery` for the worker, `web` for
gunicorn's request lines; each container is one process.

**Quirks.** Nothing restarts a crashed container unless you ask for it:
give each service `restart: unless-stopped`. Keep the scheduler to one
process, as above. Back up Postgres and the bucket yourself.

## Documentation deployment

The release workflow publishes each version of this site to GitHub Pages
next to the image; [Releasing](releasing.md) has the one-time Pages
setting and the commands.
