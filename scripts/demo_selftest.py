#!/usr/bin/env python3
"""Credential-free anti-rot check for the real D1 presenter demo.

Two stages, both executed, neither matching hard-coded prose:

1. **In-process** -- the real :class:`DemoSession` computes every live market brief and
   renders, advances and resets all four presenter steps.
2. **Served** -- the real ``ThreadingHTTPServer`` from ``scripts/demo_server.py`` is
   started on an ephemeral port and the whole presenter journey is driven over HTTP with
   ``POST /advance``. Every figure asserted at this stage is read back out of the SERVED
   bytes through the stable ``data-*`` evidence hooks and compared with what the RUNNING
   app computed. A renderer that stops emitting a figure, a server that stops advancing,
   a panel whose hook is renamed, or a count that goes stale all fail here. A check that
   never served a byte cannot see whether serving works.

The headless-browser journey over the same served pages lives in
``tests/browser/test_served_demo_ui.py`` and needs the pinned ``[demo]`` extra
(``make demo-browser``).
"""

from __future__ import annotations

import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

from demo_server import DemoSession, Handler

# Every result panel the presenter walks through. Slugs, not headings: the heading is
# presentation copy, the hook is the contract.
PANELS = (
    "summary",
    "key-claims",
    "trends",
    "competitor-moves",
    "where-to-play",
    "sources",
)


def _hook(html: str, attribute: str) -> str:
    """Read one stable ``data-*`` evidence hook out of served markup."""
    match = re.search(rf"{attribute}='([^']*)'", html) or re.search(rf'{attribute}="([^"]*)"', html)
    assert match, f"evidence hook {attribute} is missing from the served page"
    return match.group(1)


def _hooks(html: str, attribute: str) -> list[str]:
    """Read every occurrence of a ``data-*`` hook, in document order."""
    return re.findall(rf"{attribute}='([^']*)'", html) or re.findall(
        rf'{attribute}="([^"]*)"', html
    )


def check_in_process() -> None:
    session = DemoSession()
    assert len(session.briefs) == 4
    for step, brief in enumerate(session.briefs, 1):
        assert brief["requires_human_review"] is True
        assert brief["citations"]
        page = session.render()
        assert f"Step {step}/{len(session.briefs)}" in page
        assert "HUMAN REVIEW REQUIRED" in page
        if step < len(session.briefs):
            session.advance()
    assert session.at_end
    session.reset()
    assert session.idx == 0
    print("PASS demo self-test: 4/4 live market briefs rendered, advanced, and reset")


def _assert_served_brief(page: str, brief: dict[str, Any]) -> None:
    """Every figure on the served page equals what the running app computed."""
    ca = brief.get("competitor_analysis") or {}
    moves = [d for d in (ca.get("diff") or {}).get("deltas", []) if d.get("status") != "unchanged"]
    options = (ca.get("swot") or {}).get("options", [])

    assert _hook(page, "data-brief") == brief["id"]
    assert _hook(page, "data-brief-topic") == brief["topic"]
    assert _hook(page, "data-brief-market") == brief["market"]
    assert _hook(page, "data-brief-vertical") == brief["vertical"]
    assert _hook(page, "data-brief-citations") == str(len(brief["citations"]))
    assert _hook(page, "data-brief-claims") == str(len(brief["key_claims"]))
    assert _hook(page, "data-brief-trends") == str(len(brief["trends"]))
    assert _hook(page, "data-brief-moves") == str(len(moves))
    assert _hook(page, "data-brief-options") == str(len(options))
    assert _hook(page, "data-brief-sources") == str(len(brief["sources"]))
    assert _hook(page, "data-brief-review") == str(bool(brief["requires_human_review"])).lower()
    assert brief["requires_human_review"] is True
    assert _hook(page, "data-review-gate") == "required", "the maker-checker gate stopped rendering"

    panels = _hooks(page, "data-panel")
    for required in PANELS:
        assert required in panels, f"the served page lost the {required} panel hook"

    # Per-panel counts and the ranked/scored items themselves.
    assert _hook(page, "data-claim-count") == str(len(brief["key_claims"]))
    assert _hooks(page, "data-claim-citations") == [
        str(len(c.get("citations", []))) for c in brief["key_claims"]
    ]
    assert _hook(page, "data-trend-count") == str(len(brief["trends"]))
    assert _hooks(page, "data-trend") == [t["topic"] for t in brief["trends"]]
    assert _hooks(page, "data-trend-score") == [
        str(int(round(float(t["score"]) * 100))) for t in brief["trends"]
    ]
    assert _hooks(page, "data-trend-direction") == [t["direction"] for t in brief["trends"]]
    assert _hook(page, "data-move-count") == str(len(moves))
    assert _hooks(page, "data-move") == [m["competitor"] for m in moves]
    assert _hooks(page, "data-move-severity") == [m["severity"] for m in moves]
    assert _hook(page, "data-option-count") == str(len(options))
    assert _hooks(page, "data-option") == [o["id"] for o in options]
    assert _hooks(page, "data-option-score") == [
        str(int(round(float(o["score"]) * 100))) for o in options
    ]
    assert _hook(page, "data-source-count") == str(len(brief["sources"]))
    assert _hooks(page, "data-source") == [s["id"] for s in brief["sources"]]

    # The sources panel IS this demo's audit surface: every live citation must be on it.
    assert brief["citations"], "the running app produced no citations to prove"
    served_citations = set(_hooks(page, "data-citation"))
    for citation in brief["citations"]:
        assert citation["source_id"] in served_citations, (
            f"live citation {citation['source_id']} never reached the served page"
        )
        assert citation["title"] in page


def check_served() -> None:
    """Drive the REAL demo server over HTTP and assert live figures from served bytes."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.session = DemoSession()  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    session: DemoSession = server.session  # type: ignore[attr-defined]

    try:
        for index in range(len(session.briefs)):
            with urllib.request.urlopen(f"{base}/", timeout=30) as response:  # noqa: S310
                assert response.status == 200
                page = response.read().decode("utf-8")

            # The served page is at the step the served app believes it is at.
            assert _hook(page, "data-step") == str(index), f"served step marker is not {index}"
            assert _hook(page, "data-step-total") == str(len(session.briefs))
            assert _hook(page, "data-step-brief") == session.briefs[index]["id"]

            _assert_served_brief(page, session.briefs[index])

            if index < len(session.briefs) - 1:
                request = urllib.request.Request(f"{base}/advance", method="POST", data=b"")
                with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                    assert response.status in (200, 303)
            else:
                assert "Demo complete" in page, "the last served step is not the end state"

        # Restart must serve too, and must put the live session back at step one.
        with urllib.request.urlopen(f"{base}/restart", timeout=30) as response:  # noqa: S310
            restarted = response.read().decode("utf-8")
        assert response.status == 200
        assert _hook(restarted, "data-step") == "0"
        assert session.idx == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(
        "PASS served: every presenter step, panel hook, live citation and computed figure "
        "read back over HTTP from the running demo server"
    )


def main() -> int:
    check_in_process()
    check_served()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
