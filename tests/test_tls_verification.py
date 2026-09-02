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


def _warns_on_request(url):
    """Whether an actual unverified request warns, not just construction."""
    import warnings as _warnings

    from urllib3.exceptions import InsecureRequestWarning

    client = SaltApiClient(url)
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        with client._request_context():
            _warnings.warn("Unverified HTTPS request", InsecureRequestWarning)
    return [w for w in caught if issubclass(w.category, InsecureRequestWarning)]


def test_the_loopback_default_does_not_warn_on_every_request():
    # urllib3 warns per unverified request; for a check Alcali deliberately
    # skipped that is a line of noise in the log for every single call.
    assert _warns_on_request("https://127.0.0.1:8080") == []


def test_an_operator_who_disabled_verification_still_gets_the_warning(monkeypatch):
    # That one may well be a mistake, so it keeps warning.
    monkeypatch.setenv("SALT_VERIFY_TLS", "false")
    assert _warns_on_request("https://salt.example.test:8080")
