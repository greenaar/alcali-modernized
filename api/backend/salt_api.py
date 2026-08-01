"""Small, maintained client for Salt's rest_cherrypy API.

Alcali only used a narrow slice of salt-pepper, whose last release was in 2020.
Keeping that abandoned command-line client in the request path made TLS and
timeout behaviour difficult to control, so the required REST calls live here.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin

import requests


class SaltApiError(RuntimeError):
    """Raised when Salt cannot be reached or returns an invalid response."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


class SaltApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = float(os.environ.get("SALT_TIMEOUT", "30"))
        self.verify: bool | str = os.environ.get("SALT_CA_BUNDLE") or _env_bool(
            "SALT_VERIFY_TLS", True
        )
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

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
