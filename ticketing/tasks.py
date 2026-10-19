import logging

from celery import shared_task

from .adapters import adapter_for
from .models import TicketingSettings
from .sync import sync

logger = logging.getLogger(__name__)


class PollFailed(Exception):
    """At least one edition could not be polled; the others were."""


@shared_task(
    autoretry_for=(PollFailed,), retry_backoff=60, retry_jitter=True, max_retries=3
)
def poll_registrations_task():
    """Every edition with a provider API, every few minutes: polling is the
    baseline, webhooks an optimisation. Each edition
    is attempted; a failure is re-raised at the end so Celery retries with
    back-off, and only the failed editions have anything left to fetch."""
    results, failed = [], []
    for row in TicketingSettings.objects.select_related("conference"):
        adapter = adapter_for(row)
        if adapter is None:
            continue
        try:
            seen = sync(row, adapter)
        except Exception as exc:  # noqa: BLE001 - one shop down must not stop the rest
            logger.exception("Polling registrations failed for %s", row.conference)
            results.append(f"{row.conference}: failed ({exc})")
            failed.append(str(row.conference))
        else:
            results.append(f"{row.conference}: {seen} registration(s)")
    if failed:
        raise PollFailed(", ".join(failed))
    return "; ".join(results) or "No edition has a ticketing API set up"
