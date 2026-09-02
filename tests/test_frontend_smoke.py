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

pytestmark = pytest.mark.smoke

BASE_DIR = Path(__file__).resolve().parent.parent

# Warnings the app emits by design: labels that double as translation keys fall
# back to the literal, which intlify reports.
IGNORED = (
    "[intlify] Legacy API mode",
    "Not found",
    "Download the Vue Devtools",
)

ROUTES = [
    "/", "/minions", "/jobs", "/run", "/job_templates", "/schedules",
    "/conformity", "/states", "/keys", "/events", "/users", "/settings",
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
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=BASE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.poll() is not None:
            pytest.fail("runserver exited: " + server.stdout.read().decode()[-2000:])
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
        tmp.cleanup()


@pytest.fixture(scope="module")
def page(live_app):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright is not installed"
    ).sync_playwright
    base, creds = live_app
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1200})
        page = context.new_page()
        page.goto(base + "/login", wait_until="networkidle")
        page.fill("input[name=login]", creds["username"])
        page.fill("input[name=password]", creds["password"])
        page.locator(".v-card-actions button").first.click()
        page.wait_for_timeout(2000)
        assert "/login" not in page.url, "could not sign in to the built frontend"
        yield page, base, creds
        browser.close()


def _drain(messages):
    return [m for m in dict.fromkeys(messages) if not any(i in m for i in IGNORED)]


@pytest.mark.parametrize("route", ROUTES)
def test_route_renders_without_console_errors(page, route):
    page, base, _ = page
    messages = []
    page.on("console", lambda m: messages.append(f"[{m.type}] {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: messages.append(f"[pageerror] {e}"))
    page.goto(base + route, wait_until="networkidle")
    page.wait_for_timeout(1500)
    problems = _drain(messages)
    assert not problems, f"{route} reported:\n" + "\n".join(problems)


def test_job_detail_loads_the_record(page):
    page, base, creds = page
    jid, minion = creds["job"]
    page.goto(f"{base}/jobs/{jid}/{minion}", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    # The relative-URL bug produced an empty record on this nested route.
    assert jid in body and minion in body
    assert "Invalid Date" not in body


def test_tables_are_populated(page):
    page, base, _ = page
    for route, expected in [("/minions", 3), ("/keys", 6), ("/schedules", 6)]:
        page.goto(base + route, wait_until="networkidle")
        page.wait_for_timeout(1500)
        rows = page.locator("table tbody tr").count()
        assert rows >= expected, f"{route} showed {rows} rows, expected {expected}"


def test_overview_reports_a_minion_that_stopped_returning(page):
    page, base, _ = page
    page.goto(base + "/", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    # An accepted key with no returns appears nowhere else in the UI.
    assert "never-returned.example.test" in body


def test_job_view_reports_minions_that_never_replied(page):
    page, base, creds = page
    jid, _ = creds["job"]
    page.goto(base + "/jobs/" + jid, wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    assert "never returned" in body or "never-returned.example.test" in body


def test_state_costs_are_reported(page):
    page, base, _ = page
    page.goto(base + "/states", wait_until="networkidle")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    # Per-state duration and sls live in full_ret and nothing else reads them.
    assert "nginx" in body and "web.nginx" in body
    assert "30.0s" in body


def test_run_page_previews_the_blast_radius(page):
    page, base, _ = page
    page.goto(base + "/run", wait_until="networkidle")
    page.wait_for_timeout(1500)
    target = page.get_by_label("Target", exact=True)
    target.fill("*")
    page.wait_for_timeout(1500)
    body = page.locator(".v-main").inner_text()
    # Three minions are seeded; the roster comes from stored grains.
    assert "matches 3 of 3 known minions" in body


def test_job_output_is_readable_in_light_mode(page):
    page, base, creds = page
    jid, minion = creds["job"]
    page.goto("{}/jobs/{}/{}".format(base, jid, minion), wait_until="networkidle")
    page.wait_for_timeout(1500)
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
