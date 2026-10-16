"""gunicorn settings for the web process, the same on every host.

The boot contract says the web process serves on ``$PORT``. Cabotage is the
one host that hands the process a unix socket instead; it is recognised by
its socket directory, and the ``when_ready`` marker is what it waits for.
"""

import os

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


def when_ready(server):
    """Tell the host the app is up (cabotage reads this file)."""
    open("/tmp/app-initialized", "w").close()
