"""The health route every host probes.

Container hosts ask the web process whether it is alive and ready, many
times a minute, with no idea what hostname the instance answers on:
Cabotage's probes come through its TLS sidecar, Azure Container Apps' from
the platform, a plain server's from the proxy or an uptime monitor. The
answer is a bare ``200 ok`` at ``/_health/`` (Cabotage's default path),
given before Django checks the ``Host`` header and without touching the
database, so a probe never renders a page, never fails on a hostname and
never restarts a web pod because the database blinked. Whether the database
and the workers are well is a question for the maintenance pages, where the
organizers can see it; the probe only says the process answers.
"""

from django.http import HttpResponse, HttpResponseNotAllowed

#: The path, with and without the trailing slash: a probe may send either.
PATHS = ("/_health/", "/_health")


class HealthCheckMiddleware:
    """Answer the health path first, before any other middleware runs.

    It must be the first entry in ``MIDDLEWARE``: ``SecurityMiddleware`` and
    ``CommonMiddleware`` both read the ``Host`` header, which rejects a probe
    sent to the pod's address with a 400.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info not in PATHS:
            return self.get_response(request)
        if request.method not in ("GET", "HEAD"):
            return HttpResponseNotAllowed(["GET", "HEAD"])
        response = HttpResponse("ok\n", content_type="text/plain")
        response["Cache-Control"] = "no-store"
        return response
