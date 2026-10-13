"""The instance-wide pretix webhook (``/webhooks/pretix/``).

Kept for shops already pointed at it. It used to read one organizer, one
event and one secret from the environment; it now finds the edition whose
ticketing settings name the payload's organizer and event,
checks that edition's secret, and queues the same re-fetch the per-edition
receiver does (``speakers.webhooks``).
"""

import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from speakers.encryption import usable
from speakers.pretix import WEBHOOK_ACTIONS
from speakers.tasks import sync_order_task
from ticketing.models import TicketingSettings

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def pretix_webhook(request):
    if "secret" not in request.GET:
        return HttpResponseBadRequest("Missing required query parameter: secret")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON")
    if not isinstance(payload, dict):
        return HttpResponseBadRequest("Invalid pretix payload structure")
    required = {"notification_id", "organizer", "event", "code", "action"}
    if not required.issubset(payload):
        return HttpResponseBadRequest("Invalid pretix payload structure")
    if payload["action"] not in WEBHOOK_ACTIONS:
        return HttpResponseBadRequest("Unsupported pretix action")
    row = (
        TicketingSettings.objects.filter(
            organizer=payload["organizer"], event_id=payload["event"]
        )
        .select_related("conference")
        .first()
    )
    if row is None or not row.has_api:
        return HttpResponseBadRequest("No edition takes this organizer and event")
    secret = row.webhook_secret
    if not usable(secret) or not constant_time_compare(request.GET["secret"], secret):
        return HttpResponse("Unauthorized", status=401)
    code = payload["code"]
    try:
        sync_order_task.delay(row.conference_id, code)
    except Exception:  # noqa: BLE001 - broker down, or the task itself in eager mode
        logger.exception("Pretix webhook: could not queue order %s", code)
        return JsonResponse({"error": "could not queue"}, status=502)
    return JsonResponse({"queued": code}, status=202)
