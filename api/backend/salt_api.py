"""Small, maintained client for Salt's rest_cherrypy API.

Alcali only used a narrow slice of salt-pepper, whose last release was in 2020.
Keeping that abandoned command-line client in the request path made TLS and
timeout behaviour difficult to control, so the required REST calls live here.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import threading
import warnings
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from urllib3.exceptions import InsecureRequestWarning

logger = logging.getLogger(__name__)


class SaltApiError(RuntimeError):
    """Raised when Salt cannot be reached or returns an invalid response."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _is_loopback(base_url: str) -> bool:
    """Is this URL addressing the machine Alcali is running on?

    A certificate says who the far end is, which is a question with no content
    over loopback: the traffic never leaves the host, and anything able to
    intercept it is already running as some user on this machine.
    """
    host = (urlsplit(base_url).hostname or "").strip("[]")
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_quiet_hosts: set[str] = set()
_quiet_hosts_lock = threading.Lock()


def _silence_unverified_warning(base_url: str) -> None:
    """Stop urllib3 warning about unverified requests to this one host.

    Installed once, process-wide, and matched on the host in the message, so
    an unverified request anywhere else still warns. This used to be a
    warnings.catch_warnings() block around each request, which is not
    thread-safe: under gunicorn's threaded workers one request restoring the
    filters it saved put back another's warning mid-flight, and every such
    restore also reset the registry that makes a warning print only once - so
    the line came back on nearly every call rather than going away.
    """
    host = (urlsplit(base_url).hostname or "").strip("[]")
    if not host:
        return
    with _quiet_hosts_lock:
        if host in _quiet_hosts:
            return
        warnings.filterwarnings(
            "ignore",
            message=r"Unverified HTTPS request is being made to host '{}'".format(
                re.escape(host)
            ),
            category=InsecureRequestWarning,
        )
        _quiet_hosts.add(host)


def _response_detail(exc: Exception, limit: int = 500) -> str:
    """The body salt-api sent with an error, when there is one worth showing."""
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        payload = response.json()
    except ValueError:
        payload = (response.text or "").strip()
    if isinstance(payload, dict):
        payload = payload.get("return") or payload.get("error") or payload
    detail = str(payload).strip()
    if not detail:
        return ""
    if len(detail) > limit:
        detail = detail[:limit] + "..."
    return " - {}".format(detail)


class SaltApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = float(os.environ.get("SALT_TIMEOUT", "30"))
        self.verify: bool | str = self._verification_for(base_url)
        if self.verify is False and self._quiet_unverified():
            _silence_unverified_warning(base_url)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    @staticmethod
    def _verification_for(base_url: str) -> bool | str:
        """What to pass to requests as `verify`.

        A CA bundle, or an explicit SALT_VERIFY_TLS, is always honoured. With
        neither set, verification stays on for a real host and is skipped for
        loopback - where a salt-api serving a certificate for its public name
        fails on an address mismatch, and where verifying proves nothing
        anyway.
        """
        bundle = os.environ.get("SALT_CA_BUNDLE")
        if bundle:
            return bundle
        if os.environ.get("SALT_VERIFY_TLS") is not None:
            return _env_bool("SALT_VERIFY_TLS", True)
        if _is_loopback(base_url):
            logger.debug(
                "not verifying the salt-api certificate for the loopback "
                "address %s; set SALT_VERIFY_TLS=true to require it",
                base_url,
            )
            return False
        return True

    @staticmethod
    def _quiet_unverified() -> bool:
        """Whether an unverified request to salt-api should go unremarked.

        Always for the loopback default: Alcali decided to skip that check
        itself, so a warning per call is noise about something deliberate. An
        operator who set SALT_VERIFY_TLS=false still gets the warning, because
        that one may well be a mistake - unless SALT_SUPPRESS_TLS_WARNING says
        they know.
        """
        if _env_bool("SALT_SUPPRESS_TLS_WARNING", False):
            return True
        return os.environ.get("SALT_VERIFY_TLS") is None and not os.environ.get(
            "SALT_CA_BUNDLE"
        )

    def _url(self, path: str = "") -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _json_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                self._url(path),
                timeout=self.timeout,
                verify=self.verify,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            # salt-api puts the reason in the body - an unknown function, a
            # client the master has not enabled, a rejected ACL. Without it
            # the caller only ever sees "500 Server Error", which says
            # nothing about which of those it was.
            raise SaltApiError(
                "Salt API request failed: {}{}".format(exc, _response_detail(exc))
            ) from exc
        if not isinstance(payload, dict):
            raise SaltApiError("Salt API returned an unexpected response")
        return payload

    def login(self, username: str, password: str, eauth: str) -> dict[str, Any]:
        payload = self._json_request(
            "POST",
            "login",
            json={"username": username, "password": password, "eauth": eauth},
        )
        try:
            login_data = payload["return"][0]
            self.session.headers["X-Auth-Token"] = login_data["token"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SaltApiError("Salt API login response did not contain a token") from exc
        return login_data

    def low(self, load: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        lowstate = load if isinstance(load, list) else [load]
        return self._json_request("POST", "", json=lowstate)

    def local(self, target: str, function: str, **kwargs: Any) -> dict[str, Any]:
        load = {"client": "local", "tgt": target, "fun": function, **kwargs}
        return self.low(load)

    def runner(self, function: str, **kwargs: Any) -> dict[str, Any]:
        return self.low({"client": "runner", "fun": function, **kwargs})

    def wheel(self, function: str, **kwargs: Any) -> dict[str, Any]:
        return self.low({"client": "wheel", "fun": function, **kwargs})

    def req_stream(self, path: str) -> Iterator[bytes]:
        try:
            with self.session.get(
                self._url(path),
                headers={"Accept": "text/event-stream"},
                timeout=(self.timeout, None),
                verify=self.verify,
                stream=True,
            ) as response:
                response.raise_for_status()
                yield from response.iter_content(chunk_size=None)
        except requests.RequestException as exc:
            raise SaltApiError(f"Salt event stream failed: {exc}") from exc
