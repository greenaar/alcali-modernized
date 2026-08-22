#!/usr/bin/env python
"""Container health probe for the gunicorn service.

Any HTTP response below 500 counts as healthy. That is deliberate: a strict
ALLOWED_HOSTS answers the probe's request with 400, which still proves
gunicorn is accepting connections and running Django. Only a refused
connection, a timeout or a 5xx marks the container unhealthy.
"""
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("HEALTHCHECK_URL", "http://127.0.0.1:8000/")
TIMEOUT = float(os.environ.get("HEALTHCHECK_TIMEOUT", "5"))

try:
    status = urllib.request.urlopen(URL, timeout=TIMEOUT).status
except urllib.error.HTTPError as exc:
    status = exc.code
except OSError as exc:
    print(f"unhealthy: {exc}", file=sys.stderr)
    sys.exit(1)

if status >= 500:
    print(f"unhealthy: HTTP {status}", file=sys.stderr)
    sys.exit(1)
