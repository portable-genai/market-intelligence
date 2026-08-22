"""F2: the D1 presenter demo is driven through a real headless browser, not a string.

``scripts/demo_selftest.py`` starts the real server and reads the served bytes, which
covers the server/renderer path browserlessly. This file closes the other half: a pinned
headless Chromium loads the SERVED pages, clicks the presenter's own ``Next`` button
through every step, and reads each asserted figure back out of the LIVE DOM through the
stable ``data-*`` evidence hooks. Nothing here is compared against hard-coded prose; every
expectation is recomputed from the running :class:`DemoSession`.

``scripts/demo_playwright.py`` remains the presenter-paced narrated walkthrough for a
human audience. This is its gated counterpart: same server, same selectors, but asserting
live figures instead of pausing for applause.

Playwright is pinned in the ``[demo]`` extra. The browser binary is a network download, so
a fork's day-one offline gate (D3) must not depend on it: the module skips LOUDLY (run it
with ``-rs``, as ``make demo-browser`` does) when the extra or the browser is absent. It
never passes silently.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="the pinned [demo] extra is not installed"
)


def _load(name: str) -> ModuleType:
    """Import a demo script by path (``scripts/`` is not an installed package)."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


demo_server = _load("demo_server")

PANELS = ("summary", "key-claims", "trends", "competitor-moves", "where-to-play", "sources")


@pytest.fixture(scope="module")
def served() -> Iterator[tuple[str, Any]]:
    """The REAL demo server, on an ephemeral port, for the duration of the module.

    The live :class:`DemoSession` is handed back rather than a snapshot of its briefs:
    ``/restart`` recomputes them, so every expectation is read from the object the server
    is serving at the moment of the assertion.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), demo_server.Handler)
    server.session = demo_server.DemoSession()
    server.lock = threading.Lock()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", server.session
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def page() -> Iterator[Any]:
    try:
        with playwright_api.sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:  # pragma: no cover - environment-dependent
                pytest.skip(f"no pinned browser binary available: {exc}")
            context = browser.new_context(viewport={"width": 1100, "height": 900})
            yield context.new_page()
            context.close()
            browser.close()
    except NotImplementedError as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"playwright cannot run here: {exc}")


def _attrs(page: Any, selector: str, attribute: str) -> list[str]:
    """Read one attribute off every matching element, in document order."""
    return page.locator(selector).evaluate_all(
        f"els => els.map(e => e.getAttribute({attribute!r}))"
    )


def test_the_served_demo_walks_every_brief_in_a_real_browser(
    page: Any, served: tuple[str, Any]
) -> None:
    base, session = served
    page.goto(f"{base}/restart", wait_until="load")
    briefs: list[dict[str, Any]] = session.briefs

    for index, brief in enumerate(briefs):
        bar = page.locator("[data-demo='presenter-step']")
        assert bar.get_attribute("data-step") == str(index)
        assert bar.get_attribute("data-step-total") == str(len(briefs))
        assert bar.get_attribute("data-step-brief") == brief["id"]

        ca = brief.get("competitor_analysis") or {}
        moves = [
            d for d in (ca.get("diff") or {}).get("deltas", []) if d.get("status") != "unchanged"
        ]
        options = (ca.get("swot") or {}).get("options", [])

        # Figures read out of the LIVE DOM, checked against the running app.
        head = page.locator("[data-brief]")
        assert head.get_attribute("data-brief") == brief["id"]
        assert head.get_attribute("data-brief-market") == brief["market"]
        assert head.get_attribute("data-brief-vertical") == brief["vertical"]
        assert head.get_attribute("data-brief-citations") == str(len(brief["citations"]))
        assert head.get_attribute("data-brief-claims") == str(len(brief["key_claims"]))
        assert head.get_attribute("data-brief-trends") == str(len(brief["trends"]))
        assert head.get_attribute("data-brief-moves") == str(len(moves))
        assert head.get_attribute("data-brief-options") == str(len(options))
        assert head.get_attribute("data-brief-sources") == str(len(brief["sources"]))
        assert (
            head.get_attribute("data-brief-review")
            == str(bool(brief["requires_human_review"])).lower()
        )

        for panel in PANELS:
            assert page.locator(f"[data-panel='{panel}']").count() == 1, panel

        # The maker-checker gate must be visible, not merely present in the markup.
        assert page.locator("[data-review-gate='required']").is_visible()

        assert page.locator("[data-trend-count]").get_attribute("data-trend-count") == str(
            len(brief["trends"])
        )
        assert _attrs(page, "[data-trend]", "data-trend") == [t["topic"] for t in brief["trends"]]
        assert _attrs(page, "[data-trend-score]", "data-trend-score") == [
            str(int(round(float(t["score"]) * 100))) for t in brief["trends"]
        ]
        assert page.locator("[data-move-count]").get_attribute("data-move-count") == str(len(moves))
        assert _attrs(page, "[data-move]", "data-move") == [m["competitor"] for m in moves]
        assert _attrs(page, "[data-move-severity]", "data-move-severity") == [
            m["severity"] for m in moves
        ]
        assert page.locator("[data-option-count]").get_attribute("data-option-count") == str(
            len(options)
        )
        assert _attrs(page, "[data-option]", "data-option") == [o["id"] for o in options]
        assert _attrs(page, "[data-option-score]", "data-option-score") == [
            str(int(round(float(o["score"]) * 100))) for o in options
        ]
        assert _attrs(page, "[data-source]", "data-source") == [s["id"] for s in brief["sources"]]

        # Every live citation reached the DOM the audience is looking at.
        assert brief["citations"], "the running app produced no citations to prove"
        shown = set(_attrs(page, "[data-citation]", "data-citation"))
        for citation in brief["citations"]:
            assert citation["source_id"] in shown, citation["source_id"]

        if index < len(briefs) - 1:
            button = page.locator(".democtl button.next")
            assert button.is_enabled()
            button.click()
            page.wait_for_load_state("load")

    assert page.locator(".democtl button.next[disabled]").count() == 1
    assert "Demo complete" in page.content()


def test_the_restart_button_returns_the_browser_to_the_first_brief(
    page: Any, served: tuple[str, Any]
) -> None:
    base, session = served
    page.goto(f"{base}/", wait_until="load")
    page.locator(".democtl button.restart").click()
    page.wait_for_load_state("load")
    bar = page.locator("[data-demo='presenter-step']")
    assert bar.get_attribute("data-step") == "0"
    assert session.idx == 0
    assert page.locator("[data-brief]").get_attribute("data-brief") == session.briefs[0]["id"]
