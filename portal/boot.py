"""The boot contract: what an instance needs to start.

An instance is one container image, started with environment variables.
A few of them are mandatory in production, and a missing one must fail
the boot with its name rather than surface later as a 500, a lost upload
or an email that never left. ``check`` is called from the settings module
and raises ``ImproperlyConfigured`` listing every missing variable at
once, so an operator fixes them in one round.

Nothing is enforced while ``DEBUG`` is on or under pytest, where the
console email backend and local files stand in for the services;
``BOOT_CHECK=0`` turns the check off elsewhere, for a one-off shell.
"""

from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

#: Variables an instance needs whatever the environment.
ALWAYS = (("SECRET_KEY", "Django's secret key; any long random string"),)

#: Variables an instance needs in production, each with an accepted
#: alternative (any one of the names satisfies the line) and a reason.
PRODUCTION = (
    (("DJANGO_ALLOWED_HOSTS",), "the hostnames the portal answers on, comma-separated"),
    (("DATABASE_URL",), "the Postgres connection URL"),
    (("CELERY_BROKER_URL", "REDIS_URL"), "the Redis URL the worker and beat share"),
    (("FERNET_KEY", "FERNET_KEYS"), "the key for fields encrypted at rest"),
    (
        ("DJANGO_EMAIL_HOST", "EMAIL_URL"),
        "the SMTP server that sends the portal's email",
    ),
    (("DJANGO_DEFAULT_FROM_EMAIL",), "the address the portal's email comes from"),
    (("AWS_ACCESS_KEY_ID",), "the object storage access key (S3 API)"),
    (("AWS_SECRET_ACCESS_KEY",), "the object storage secret key"),
    (("AWS_STORAGE_BUCKET_NAME",), "the bucket for uploads"),
    (("AWS_S3_ENDPOINT_URL",), "the object storage endpoint (any S3-compatible host)"),
)


def missing(env, production):
    """``[(names, reason)]`` for every requirement ``env`` does not meet."""
    gaps = []
    for name, reason in ALWAYS:
        if not env.get(name, "").strip():
            gaps.append(((name,), reason))
    if production:
        for names, reason in PRODUCTION:
            if not any(env.get(name, "").strip() for name in names):
                gaps.append((names, reason))
    return gaps


def check(env, debug):
    """Raise ``ImproperlyConfigured`` naming every missing variable."""
    if env.get("BOOT_CHECK", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    gaps = missing(env, production=not debug)
    if not gaps:
        return
    lines = [f"  {' or '.join(names)}: {reason}" for names, reason in gaps]
    raise ImproperlyConfigured(
        "Flashlights cannot start: the environment is missing\n"
        + "\n".join(lines)
        + '\nSee docs/developer/deployment.md, "The boot contract".'
    )


def switch(env, *names, default="false"):
    """The first of ``names`` that is set, parsed as a boolean."""
    for name in names:
        if name in env:
            return env[name].strip().lower() not in ("0", "false", "no", "off", "")
    return default == "true"


def email_url(url):
    """``smtp://user:password@host:port/?tls=true`` as Django email settings.

    One variable instead of six, the shape managed platforms hand out.
    ``smtps://`` means SSL; ``?tls=true`` means STARTTLS; a missing port
    is 587 with TLS, 465 with SSL, 25 otherwise.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("smtp", "smtps"):
        raise ImproperlyConfigured(
            f"EMAIL_URL must start with smtp:// or smtps://, not {url!r}"
        )
    query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
    use_ssl = parts.scheme == "smtps"
    use_tls = not use_ssl and query.get("tls", "").lower() in ("1", "true", "yes")
    port = parts.port or (465 if use_ssl else 587 if use_tls else 25)
    return {
        "EMAIL_HOST": parts.hostname or "",
        "EMAIL_PORT": port,
        "EMAIL_HOST_USER": unquote(parts.username or ""),
        "EMAIL_HOST_PASSWORD": unquote(parts.password or ""),
        "EMAIL_USE_TLS": use_tls,
        "EMAIL_USE_SSL": use_ssl,
    }
