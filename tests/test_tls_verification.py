"""Which certificate verification each salt-api URL gets.

salt-api commonly serves the certificate for the master's public name while
Alcali talks to it over loopback, where that certificate cannot match and where
verifying it establishes nothing: the traffic never leaves the host.
"""
import pytest

from api.backend.salt_api import SaltApiClient


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("SALT_VERIFY_TLS", raising=False)
    monkeypatch.delenv("SALT_CA_BUNDLE", raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8080",
        "https://127.0.0.1:8080/",
        "https://localhost:8080",
        "https://[::1]:8080",
        "https://127.1.2.3:8080",
    ],
)
def test_loopback_is_not_verified_by_default(url):
    assert SaltApiClient(url).verify is False


@pytest.mark.parametrize(
    "url",
    [
        "https://salt.example.test:8080",
        "https://10.0.0.5:8080",
        "https://172.16.2.12:8080",
    ],
)
def test_a_real_host_is_still_verified_by_default(url):
    assert SaltApiClient(url).verify is True


def test_an_explicit_setting_wins_over_the_loopback_default(monkeypatch):
    monkeypatch.setenv("SALT_VERIFY_TLS", "true")
    assert SaltApiClient("https://127.0.0.1:8080").verify is True
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    assert SaltApiClient("https://salt.example.test:8080").verify is False


def test_a_ca_bundle_wins_over_everything(monkeypatch):
    monkeypatch.setenv("SALT_CA_BUNDLE", "/etc/alcali/tls/salt-ca.pem")
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    assert SaltApiClient("https://127.0.0.1:8080").verify == "/etc/alcali/tls/salt-ca.pem"


@pytest.fixture(autouse=True)
def isolated_warning_filters():
    """The quiet-host filter is process-wide; keep each test's to itself."""
    import warnings as _warnings

    from api.backend import salt_api

    with _warnings.catch_warnings():
        salt_api._quiet_hosts.clear()
        yield
        salt_api._quiet_hosts.clear()


def _unverified_warning(host):
    """What urllib3 emits for an unverified request, message included."""
    import warnings as _warnings

    from urllib3.exceptions import InsecureRequestWarning

    _warnings.warn(
        "Unverified HTTPS request is being made to host '{}'. Adding certificate "
        "verification is strongly advised.".format(host),
        InsecureRequestWarning,
    )


def _warns_on_request(url, host=None):
    """Whether an unverified request to `host` warns once the client exists."""
    import warnings as _warnings
    from urllib.parse import urlsplit

    from urllib3.exceptions import InsecureRequestWarning

    host = host or urlsplit(url).hostname
    with _warnings.catch_warnings(record=True) as caught:
        # "always" first, so only the client's own filter can hide it.
        _warnings.filterwarnings("always", category=InsecureRequestWarning)
        SaltApiClient(url)
        _unverified_warning(host)
    return [w for w in caught if issubclass(w.category, InsecureRequestWarning)]


def test_the_loopback_default_does_not_warn_on_every_request():
    # urllib3 warns per unverified request; for a check Alcali deliberately
    # skipped that is a line of noise in the log for every single call.
    assert _warns_on_request("https://127.0.0.1:8080") == []
    assert _warns_on_request("https://[::1]:8080") == []


def test_an_operator_who_disabled_verification_still_gets_the_warning(monkeypatch):
    # That one may well be a mistake, so it keeps warning.
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    assert _warns_on_request("https://salt.example.test:8080")
    assert _warns_on_request("https://127.0.0.1:8080")


def test_the_warning_can_be_suppressed_explicitly(monkeypatch):
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    monkeypatch.setenv("SALT_SUPPRESS_TLS_WARNING", "true")
    assert _warns_on_request("https://127.0.0.1:8080") == []
    assert _warns_on_request("https://salt.example.test:8080") == []


def test_suppression_is_limited_to_the_salt_api_host(monkeypatch):
    # Some other unverified request in the same process is not Alcali's call
    # to excuse.
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    monkeypatch.setenv("SALT_SUPPRESS_TLS_WARNING", "true")
    assert _warns_on_request("https://salt.example.test:8080", host="elsewhere.test")
    assert _warns_on_request("https://127.0.0.1:8080", host="127.0.0.10")


def test_a_verified_client_suppresses_nothing(monkeypatch):
    monkeypatch.setenv("SALT_SUPPRESS_TLS_WARNING", "true")
    assert _warns_on_request("https://salt.example.test:8080")


def test_suppression_holds_across_threads():
    # The old per-request catch_warnings() block raced under gunicorn's
    # threaded workers: one thread restoring its saved filters dropped the
    # other's suppression mid-request.
    import threading
    import warnings as _warnings

    from urllib3.exceptions import InsecureRequestWarning

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.filterwarnings("always", category=InsecureRequestWarning)
        SaltApiClient("https://127.0.0.1:8080")

        def hammer():
            for _ in range(200):
                SaltApiClient("https://127.0.0.1:8080")
                _unverified_warning("127.0.0.1")

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert not [w for w in caught if issubclass(w.category, InsecureRequestWarning)]
