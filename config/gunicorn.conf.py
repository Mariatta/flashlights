"""gunicorn settings for the web process, the same on every host.

The boot contract says the web process serves on ``$PORT``. Cabotage is the
one host that hands the process a unix socket instead; it is recognised by
its socket directory, and the ``when_ready`` marker is what it waits for.
The hosts' probes of ``/_health/`` are kept out of the access log, which
would otherwise be mostly probes.
"""

import logging
import os

#: ``portal.health.PATHS``, repeated here so the config imports nothing
#: from the app before gunicorn has set the import path up.
HEALTH_PATHS = ("/_health/", "/_health")

CABOTAGE_SOCKET_DIR = "/var/run/cabotage"

if os.path.isdir(CABOTAGE_SOCKET_DIR):
    bind = f"unix:{CABOTAGE_SOCKET_DIR}/cabotage.sock"
else:
    bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
backlog = 2048
preload_app = True
max_requests = 2048
max_requests_jitter = 128

worker_connections = 1000
timeout = 60
keepalive = 2

errorlog = "-"
loglevel = "info"
accesslog = "-"


class NotAHealthProbe(logging.Filter):
    """Drop the access line of a health probe (the ``U`` atom is the path)."""

    def filter(self, record):
        atoms = record.args
        return not (isinstance(atoms, dict) and atoms.get("U") in HEALTH_PATHS)


def when_ready(server):
    """Tell the host the app is up (cabotage reads this file), and quiet the
    probes. The workers are forked after this hook, so they inherit the
    filter."""
    server.log.access_log.addFilter(NotAHealthProbe())
    open("/tmp/app-initialized", "w").close()
