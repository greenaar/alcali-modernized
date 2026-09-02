"""Walk the built frontend and fail on any console error.

Every defect fixed in 3008.2.1 was a Vue 2 or Vuetify 2 construct that the
runtime ignores rather than rejecting: the build stayed green while pages
rendered empty tables, dead dropdowns and 404ing detail views. Loading each
route in a real browser and asserting a clean console is what catches that
class of regression.

Opt in with `pytest -m smoke`. Needs the frontend built into dist/ and
Playwright's chromium available (`playwright install chromium`).
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:  # collected, then skipped, when playwright is absent
    PlaywrightTimeout = Exception

pytestmark = pytest.mark.smoke

BASE_DIR = Path(__file__).resolve().parent.parent

# Warnings the app emits by design: labels that double as translation keys fall
# back to the literal, which intlify reports.
IGNORED = (
    "[intlify] Legacy API mode",
    "Not found",
    "Download the Vue Devtools",
    # There is no Salt master here, so /api/event_stream/ answers 503 and the
    # browser logs the failed EventSource. That is the endpoint reporting an
    # unreachable master correctly; test_status_card_reports_no_master asserts
    # the UI acts on it. Kept to these two exact strings so any other failing
    # request still fails the run.
    "Failed to load resource: the server responded with a status of 503",
    "EventSource's response has a status 503",
)

ROUTES = [
    "/", "/minions", "/jobs", "/run", "/job_templates", "/schedules",
    "/conformity", "/states", "/keys", "/events", "/users", "/settings",
    "/beacons", "/orchestrate",
    "/search?q=salt",
]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_app():
    """A migrated, seeded database served by runserver on a free port."""
    if not (BASE_DIR / "dist" / "index.html").exists():
        pytest.skip("frontend is not built; run `pnpm build` first")

    tmp = tempfile.TemporaryDirectory()
    env = dict(
        os.environ,
        # No master here. A runner whose networking does not refuse the
        # connection outright would otherwise spend SALT_TIMEOUT on every
        # event-stream reconnection, and the frontend reconnects for as long
        # as the page is open.
        SALT_URL="https://127.0.0.1:1",
        SALT_TIMEOUT="1",
        DB_BACKEND="sqlite3",
        DB_NAME=str(Path(tmp.name) / "smoke.sqlite3"),
        SECRET_KEY="smoke-tests-only-secret-key-at-least-32-bytes",
        DJANGO_DEBUG="",
        ALLOWED_HOSTS="127.0.0.1 localhost",
        PYTHONPATH=str(BASE_DIR),
    )
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=BASE_DIR, env=env, check=True, capture_output=True,
    )
    creds = json.loads(subprocess.run(
        [sys.executable, "-c",
         "import django,json;django.setup();"
         "from tests.smoke.seed import create_returner_tables, seed;"
         "create_returner_tables();print(json.dumps(seed()))"],
        cwd=BASE_DIR, env=dict(env, DJANGO_SETTINGS_MODULE="config.settings"),
        check=True, capture_output=True, text=True,
    ).stdout.strip().splitlines()[-1])

    port = _free_port()
    # runserver logs a line per request and nothing reads this stream while the
    # tests run. On a pipe that fills the kernel's 64K buffer, and the server
    # then blocks inside send_response: the port still accepts connections, so
    # it looks alive, but no reply is ever finished and navigation hangs until
    # the timeout. A file has no such limit, and it keeps the log readable for
    # the failure messages below.
    global SERVER_LOG
    SERVER_LOG = Path(tmp.name) / "runserver.log"
    log = SERVER_LOG.open("wb")
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=BASE_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.poll() is not None:
            pytest.fail("runserver exited: " + _server_log())
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("runserver never accepted a connection")
    try:
        yield base, creds
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()
        tmp.cleanup()


@pytest.fixture(scope="module")
def signed_in_context(live_app):
    """One browser, signed in once. The token lives in the context's storage,
    so every page opened from it is already authenticated."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright is not installed"
    ).sync_playwright
    base, creds = live_app
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1200})
        page = context.new_page()
        page.goto(base + "/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[name=login]", timeout=30000)
        page.fill("input[name=login]", creds["username"])
        page.fill("input[name=password]", creds["password"])
        page.locator(".v-card-actions button").first.click()
        page.wait_for_timeout(2000)
        assert "/login" not in page.url, "could not sign in to the built frontend"
        page.close()
        yield context, base, creds
        browser.close()


@pytest.fixture()
def page(signed_in_context):
    """A fresh tab per test.

    Sharing one page across the module let every test inherit the last one's
    state: the layout holds an event stream open, each test added console
    listeners that were never removed, and a browser allows only six
    connections per host. Whatever leaks, it accumulates until a navigation
    cannot get a connection and times out while the server is plainly still
    answering - which is what CI saw, passing seventeen tests and then failing
    every one after. A page per test bounds all of it, and closing the page
    tears the event stream down deterministically.
    """
    context, base, creds = signed_in_context
    page = context.new_page()
    try:
        yield page, base, creds
    finally:
        page.close()


NAV_TIMEOUT = 45000

# Set by live_app so a navigation failure can quote what the server was doing.
SERVER_LOG = None


def _server_log(limit=2000):
    """The tail of runserver's own log, for failure messages."""
    if not SERVER_LOG or not SERVER_LOG.exists():
        return "(no server log)"
    return SERVER_LOG.read_text(errors="replace")[-limit:]


def visit(page, url, settle=1200, attempts=2):
    """Navigate and wait for the app shell, not for network silence.

    The frontend keeps an event stream open, so the network never reliably
    goes quiet and `networkidle` is a race that a slow runner loses.

    Navigation is retried once: a shared runner can stall long enough to miss
    a single attempt, and a flaky smoke run teaches people to ignore it. If
    both attempts fail the error says whether the server was still answering,
    which is the first thing worth knowing.
    """
    last = None
    for attempt in range(attempts):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            page.wait_for_selector(".v-main", state="attached", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(settle)
            return
        except PlaywrightTimeout as exc:
            last = exc
    raise AssertionError(
        "could not load {} after {} attempts; the server was {}.\n{}\n"
        "--- last of the server log ---\n{}".format(
            url, attempts, _server_state(url), last, _server_log()
        )
    )


def _server_state(url):
    """Whether the application still answers at all, for the failure message."""
    import urllib.error
    import urllib.request

    root = "/".join(url.split("/")[:3])
    try:
        with urllib.request.urlopen(root + "/api/version/", timeout=10) as response:
            return "answering (HTTP {})".format(response.status)
    except urllib.error.HTTPError as exc:
        return "answering (HTTP {})".format(exc.code)
    except Exception as exc:  # noqa: BLE001 - any failure is the answer
        return "not answering ({})".format(exc)


def _drain(messages):
    return [m for m in dict.fromkeys(messages) if not any(i in m for i in IGNORED)]


@pytest.mark.parametrize("route", ROUTES)
def test_route_renders_without_console_errors(page, route):
    page, base, _ = page
    messages = []
    page.on("console", lambda m: messages.append(f"[{m.type}] {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: messages.append(f"[pageerror] {e}"))
    visit(page, base + route, settle=1500)
    problems = _drain(messages)
    assert not problems, f"{route} reported:\n" + "\n".join(problems)


def test_job_detail_loads_the_record(page):
    page, base, creds = page
    jid, minion = creds["job"]
    visit(page, f"{base}/jobs/{jid}/{minion}", settle=1500)
    body = page.locator(".v-main").inner_text()
    # The relative-URL bug produced an empty record on this nested route.
    assert jid in body and minion in body
    assert "Invalid Date" not in body


def test_tables_are_populated(page):
    page, base, _ = page
    for route, expected in [("/minions", 3), ("/keys", 6), ("/schedules", 6)]:
        visit(page, base + route, settle=1500)
        rows = page.locator("table tbody tr").count()
        assert rows >= expected, f"{route} showed {rows} rows, expected {expected}"


def test_overview_reports_a_minion_that_stopped_returning(page):
    page, base, _ = page
    visit(page, base + "/", settle=1500)
    body = page.locator(".v-main").inner_text()
    # An accepted key with no returns appears nowhere else in the UI.
    assert "never-returned.example.test" in body


def test_job_view_reports_minions_that_never_replied(page):
    page, base, creds = page
    jid, _ = creds["job"]
    visit(page, base + "/jobs/" + jid, settle=1500)
    body = page.locator(".v-main").inner_text()
    assert "never returned" in body or "never-returned.example.test" in body


def test_state_costs_are_reported(page):
    page, base, _ = page
    visit(page, base + "/states", settle=1500)
    body = page.locator(".v-main").inner_text()
    # Per-state duration and sls live in full_ret and nothing else reads them.
    assert "nginx" in body and "web.nginx" in body
    assert "30.0s" in body


def test_run_page_previews_the_blast_radius(page):
    page, base, _ = page
    visit(page, base + "/run", settle=1500)
    target = page.get_by_label("Target", exact=True)
    target.fill("*")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    # Three minions are seeded; the roster comes from stored grains.
    assert "matches 3 of 3 known minions" in body


def test_job_output_is_readable_in_light_mode(page):
    page, base, creds = page
    jid, minion = creds["job"]
    visit(page, "{}/jobs/{}/{}".format(base, jid, minion), settle=1500)
    panel = page.evaluate("""() => {
      const el = document.querySelector('.ansiStyle');
      if (!el) return null;
      const cs = getComputedStyle(el);
      const parse = c => (c.match(/\\d+/g) || []).slice(0, 3).map(Number);
      const bg = parse(cs.backgroundColor), fg = parse(cs.color);
      const lum = c => 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2];
      return {contrast: Math.abs(lum(fg) - lum(bg)),
              coloured: !!el.querySelector('span[style*="color"]'),
              text: (el.innerText || '').trim().length};
    }""")
    assert panel and panel["text"] > 0, "no job output rendered"
    # ansi2html's colours arrive in a <style> block that the sanitiser drops,
    # so the panel used to be black on black under the default light theme.
    assert panel["contrast"] > 60, "job output has too little contrast to read"
    assert panel["coloured"], "ansi colours did not survive sanitising"


def test_state_table_sorts_when_a_header_is_clicked(page):
    page, base, _ = page
    visit(page, base + "/states", settle=1500)

    def first_state():
        return page.locator("table tbody tr td").first.inner_text().strip()

    before = first_state()
    # This table passes a plain sort-by rather than binding it, which used to
    # mean header clicks emitted an update nobody listened to.
    page.locator("table thead th", has_text="State").first.click()
    page.wait_for_timeout(600)
    after = first_state()
    assert after != before, "clicking a column header did not reorder the table"


def test_run_page_controls_fit_their_row(page):
    page, base, _ = page
    visit(page, base + "/run", settle=1500)
    overflow = page.evaluate("""() => {
      const row = document.querySelector('.v-window-item .v-row');
      if (!row) return null;
      const bounds = row.getBoundingClientRect();
      return Array.from(row.children)
        .filter(c => c.getBoundingClientRect().right > bounds.right + 1)
        .map(c => c.className);
    }""")
    assert overflow == [], "columns overflow the row: {}".format(overflow)


def test_status_card_reports_no_master(page):
    page, base, _ = page
    visit(page, base + "/", settle=2500)
    status = page.locator(".v-card", has_text="Status").first.inner_text()
    # No master is reachable here, and the indicator has to say so without
    # waiting for a reload: it only ever moved towards "OK" before.
    assert "NOT OK" in status.upper().replace("_", " ")
