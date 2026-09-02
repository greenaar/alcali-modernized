"""Small, maintained client for Salt's rest_cherrypy API.

Alcali only used a narrow slice of salt-pepper, whose last release was in 2020.
Keeping that abandoned command-line client in the request path made TLS and
timeout behaviour difficult to control, so the required REST calls live here.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
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


class SaltApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = float(os.environ.get("SALT_TIMEOUT", "30"))
        self.verify: bool | str = self._verification_for(base_url)
        self._loopback_default = (
            self.verify is False
            and os.environ.get("SALT_VERIFY_TLS") is None
            and not os.environ.get("SALT_CA_BUNDLE")
        )
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

    @contextmanager
    def _request_context(self):
        """Silence the unverified-request warning for the loopback default.

        urllib3 warns on every unverified request. Where Alcali itself decided
        to skip the check that is one line of noise per call for something
        deliberate; an operator who set SALT_VERIFY_TLS=false still gets the
        warning, because that one may well be a mistake.
        """
        if not self._loopback_default:
            yield
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            yield

    def _url(self, path: str = "") -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _json_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with self._request_context():
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
            raise SaltApiError(f"Salt API request failed: {exc}") from exc
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
            with self._request_context(), self.session.get(
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
