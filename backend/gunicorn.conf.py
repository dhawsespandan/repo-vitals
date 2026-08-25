"""Gunicorn configuration (§3, §4.2).

One worker, threaded. The `gthread` worker class is *required*: RepoVitals
runs fire-and-forget background threads inside the request worker (no
Celery/Redis, D-list §12), and the default sync worker is not designed for a
mixed request + background-thread process. One worker also means exactly one
copy of the embedding model in memory (§8, D7).
"""

import multiprocessing  # noqa: F401  (documented: intentionally unused)
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Never scale these up: Render free = 750 instance-hours/month, i.e. exactly
# one always-on service, and 512 MB RAM holds exactly one embedding model.
workers = 1
worker_class = "gthread"
threads = 8

# Scans and report generations run in background threads, but a request that
# does hit a slow upstream must not be killed mid-flight.
timeout = 300
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
