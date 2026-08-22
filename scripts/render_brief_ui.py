#!/usr/bin/env python3
"""Render the D1 audit-first console from the demo JSON into static HTML pages.

Server-side, dependency-free rendering of a cited :class:`MarketBrief` (summary, key claims
with provenance, trend scores, the competitor-move diff, the ranked where-to-play options,
the source list, and the maker-checker "human review required" banner). It reuses the exact
palette of the thin Next.js console so screenshots match the live UI, and runs entirely
offline over the obviously-fictional synthetic briefs written by ``scripts/demo.py``.

    PYTHONPATH=src python scripts/demo.py
    PYTHONPATH=src python scripts/render_brief_ui.py scripts/out

Writes ``index.html`` (a small chooser) plus one ``<brief-id>.html`` per brief. The
rendering functions are also imported by ``scripts/demo_server.py`` for the presenter demo.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SEV_COLOR = {
    "low": ("#eef2f7", "#546b8b"),
    "medium": ("#fef3c7", "#92400e"),
    "high": ("#ffedd5", "#c2410c"),
    "critical": ("#fee2e2", "#b91c1c"),
}
SOURCE_LABEL = {
    "web": "WEB",
    "internal": "INTERNAL",
    "filing": "FILING",
    "news": "NEWS",
    "report": "REPORT",
    "other": "SRC",
}
MARKET_LABEL = {"JP": "Japan", "AU": "Australia", "SG": "Singapore"}
VERTICAL_LABEL = {"banking": "Banking", "online_retail": "Online retail"}

CSS = """
:root{--ink-50:#f5f7fa;--ink-100:#e6ebf2;--ink-200:#cdd7e4;--ink-300:#a6b6cc;
--ink-400:#7790ae;--ink-500:#546b8b;--ink-600:#3f5470;--ink-700:#33445b;--ink-800:#1f2a3a;
--brand-50:#eef4ff;--brand-100:#dbe7ff;--brand-600:#2945d6;--brand-700:#2237ad;
--ok:#059669;--warn:#d97706;--warn-bg:#fffbeb;
--shadow:0 1px 2px rgba(11,16,26,.06),0 8px 24px rgba(11,16,26,.06);}
*{box-sizing:border-box}
body{margin:0;background:var(--ink-50);color:var(--ink-800);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
font-size:14px;line-height:1.5;padding:24px 18px}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:18px;margin:0 0 2px}
.sub{color:var(--ink-500);font-size:13px;margin:0 0 16px}
.sub b{color:var(--ink-800)}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;
border:1px solid var(--brand-100);background:var(--brand-50);color:var(--brand-700);margin-right:6px}
.panel{border:1px solid var(--ink-200);background:#fff;border-radius:10px;box-shadow:var(--shadow);margin-bottom:16px}
.panel>h2{border-bottom:1px solid var(--ink-100);padding:11px 16px;margin:0;font-size:13px;font-weight:600;color:var(--ink-800)}
.panel>.body{padding:16px}
.review{border:1px solid #fcd34d;background:var(--warn-bg);color:#92400e;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;margin-bottom:14px}
.summary{font-size:14px;line-height:1.6}
.row{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--ink-100)}
.row:last-child{border-bottom:0}
.sev{font-size:11px;font-weight:700;padding:1px 7px;border-radius:5px;white-space:nowrap}
.muted{color:var(--ink-400);font-size:12px}
.bar{flex:0 0 120px;height:8px;border-radius:6px;background:var(--ink-100);border:1px solid var(--ink-200);overflow:hidden}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,#3a60f0,#2945d6)}
.cites{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.cite{display:flex;gap:8px;align-items:baseline;border:1px solid var(--ink-200);background:var(--ink-50);border-radius:7px;padding:7px 10px}
.cite .src{font-family:ui-monospace,Menlo,monospace;font-size:11px;font-weight:600;color:var(--brand-700);background:var(--brand-50);border:1px solid var(--brand-100);border-radius:5px;padding:1px 6px;white-space:nowrap}
.cite .title{font-size:12px;color:var(--ink-700)}
.cite .id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-500);margin-left:auto;white-space:nowrap}
.cite a{color:var(--brand-600);text-decoration:none;font-size:11px}
a.choose{display:block;padding:10px 12px;border:1px solid var(--ink-200);border-radius:8px;background:#fff;margin-bottom:8px;text-decoration:none;color:var(--ink-800)}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
        f"<div class='wrap'>{body}</div></body></html>"
    )


def _citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "<div class='muted'>(no citations)</div>"
    rows = []
    for c in citations:
        label = SOURCE_LABEL.get(str(c.get("source_type")), "SRC")
        url = c.get("url") or ""
        link = f"<a href='{esc(url)}'>open</a>" if url else ""
        rows.append(
            f"<div class='cite' data-citation='{esc(c.get('source_id'))}' data-citation-type='{esc(c.get('source_type'))}'>"
            f"<span class='src'>{esc(label)}</span>"
            f"<span class='title'>{esc(c.get('title'))}</span>"
            f"<span class='id'>{esc(c.get('source_id'))}</span>{link}"
            "</div>"
        )
    return f"<div class='cites' data-citation-count='{len(citations)}'>" + "".join(rows) + "</div>"


def _panel(title: str, body: str, slug: str) -> str:
    """One result panel with a stable, styling-independent ``data-panel`` hook (F2).

    ``slug`` is deliberately hand-given rather than derived from ``title``: the heading is
    presentation copy that a presenter may reword, while the hook is the contract that
    ``scripts/demo_selftest.py`` and ``tests/browser/test_served_demo_ui.py`` assert on.
    """
    return (
        f"<div class='panel' data-panel='{esc(slug)}'><h2>{esc(title)}</h2>"
        f"<div class='body' data-panel-body='{esc(slug)}'>{body}</div></div>"
    )


def render_brief(data: dict[str, Any]) -> str:
    """Render one cited MarketBrief dict into a standalone HTML page."""
    market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
    vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
    ca = data.get("competitor_analysis") or {}
    claim_list = data.get("key_claims", [])
    trend_list = data.get("trends", [])
    # The diff panel deliberately hides `unchanged` deltas, so the MOVE figure is the
    # count of what is actually shown, not the raw delta count.
    moves = [d for d in (ca.get("diff") or {}).get("deltas", []) if d.get("status") != "unchanged"]
    options = (ca.get("swot") or {}).get("options", [])
    source_list = data.get("sources", [])
    brief_citations = data.get("citations", [])

    # F2 evidence hooks: the load-bearing figures of one brief, in one stable element,
    # so an anti-rot check reads what the app COMPUTED rather than matching prose.
    head = (
        f"<div data-brief='{esc(data.get('id'))}' "
        f"data-brief-topic='{esc(data.get('topic'))}' "
        f"data-brief-market='{esc(data.get('market'))}' "
        f"data-brief-vertical='{esc(data.get('vertical'))}' "
        f"data-brief-citations='{len(brief_citations)}' "
        f"data-brief-claims='{len(claim_list)}' "
        f"data-brief-trends='{len(trend_list)}' "
        f"data-brief-moves='{len(moves)}' "
        f"data-brief-options='{len(options)}' "
        f"data-brief-sources='{len(source_list)}' "
        f"data-brief-review='{str(bool(data.get('requires_human_review'))).lower()}'></div>"
        f"<h1>Market brief — {esc(data.get('topic'))}</h1>"
        f"<p class='sub'><span class='pill'>{esc(market)}</span>"
        f"<span class='pill'>{esc(vertical)}</span> id <b>{esc(data.get('id'))}</b></p>"
    )
    review = ""
    if data.get("requires_human_review"):
        review = (
            "<div class='review' data-review-gate='required'>HUMAN REVIEW REQUIRED — maker-checker "
            "gate. Do not act on this brief until a qualified strategist signs off.</div>"
        )

    summary = _panel("Summary", f"<div class='summary'>{esc(data.get('summary'))}</div>", "summary")

    claims_rows = []
    for claim in claim_list:
        claims_rows.append(
            f"<div class='row' data-claim-subject='{esc(claim.get('subject'))}' "
            f"data-claim-citations='{len(claim.get('citations', []))}'>"
            f"<div style='flex:1'>{esc(claim.get('text'))}"
            f"{_citations(claim.get('citations', []))}</div></div>"
        )
    claims = _panel(
        "Key claims (cited)",
        f"<div data-claim-count='{len(claim_list)}'>"
        + ("".join(claims_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "key-claims",
    )

    trend_rows = []
    for trend in trend_list:
        pct = int(round(float(trend.get("score", 0.0)) * 100))
        trend_rows.append(
            f"<div class='row' data-trend='{esc(trend.get('topic'))}' "
            f"data-trend-score='{pct}' data-trend-direction='{esc(trend.get('direction'))}'>"
            f"<div style='flex:1'>{esc(trend.get('topic'))} "
            f"<span class='muted'>· {esc(trend.get('direction'))} · "
            f"{esc(trend.get('mentions'))} mention(s), {esc(trend.get('distinct_sources'))} source(s)</span></div>"
            f"<div class='bar'><span style='width:{pct}%'></span></div>"
            f"<div class='muted'>{pct}%</div></div>"
        )
    trends = _panel(
        "Trends",
        f"<div data-trend-count='{len(trend_list)}'>"
        + ("".join(trend_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "trends",
    )

    diff_rows = []
    for delta in moves:
        bg, fg = SEV_COLOR.get(str(delta.get("severity")), SEV_COLOR["medium"])
        changed = ", ".join(delta.get("changed_fields", []))
        change_note = (
            f"<div class='muted'>changed: {esc(changed)} {esc(delta.get('before'))} -> {esc(delta.get('after'))}</div>"
            if changed
            else ""
        )
        diff_rows.append(
            f"<div class='row' data-move='{esc(delta.get('competitor'))}' "
            f"data-move-status='{esc(delta.get('status'))}' "
            f"data-move-severity='{esc(delta.get('severity'))}'>"
            f"<span class='sev' style='background:{bg};color:{fg}'>{esc(delta.get('severity'))}</span>"
            f"<div style='flex:1'><b>{esc(delta.get('competitor'))}</b> "
            f"<span class='muted'>{esc(delta.get('status'))}</span> — {esc(delta.get('summary'))}"
            f"{change_note}{_citations(delta.get('citations', []))}</div></div>"
        )
    diff = _panel(
        "Competitor moves (deterministic diff)",
        f"<div data-move-count='{len(moves)}'>"
        + ("".join(diff_rows) or "<div class='muted'>no material moves</div>")
        + "</div>",
        "competitor-moves",
    )

    play_rows = []
    for opt in options:
        pct = int(round(float(opt.get("score", 0.0)) * 100))
        play_rows.append(
            f"<div class='row' data-option='{esc(opt.get('id'))}' data-option-score='{pct}'>"
            f"<div style='flex:1'>{esc(opt.get('title'))} "
            f"<span class='muted'>· attractiveness {esc(opt.get('attractiveness'))}, "
            f"right-to-win {esc(opt.get('right_to_win'))}</span></div>"
            f"<div class='bar'><span style='width:{pct}%'></span></div>"
            f"<div class='muted'>{pct}%</div></div>"
        )
    play = _panel(
        "Where to play (ranked, deterministic)",
        f"<div data-option-count='{len(options)}'>"
        + ("".join(play_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "where-to-play",
    )

    src_rows = []
    for source in source_list:
        src_rows.append(
            f"<div class='row' data-source='{esc(source.get('id'))}'>"
            f"<div style='flex:1'><b>{esc(source.get('id'))}</b> "
            f"{esc(source.get('title'))} <span class='muted'>({esc(source.get('publisher'))})</span></div></div>"
        )
    sources = _panel(
        "Sources",
        f"<div data-source-count='{len(source_list)}'>"
        + ("".join(src_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "sources",
    )

    body = head + review + summary + claims + trends + diff + play + sources
    return _page(f"Market brief — {data.get('topic')}", body)


def render_index(briefs: list[tuple[str, dict[str, Any]]]) -> str:
    rows = []
    for fname, data in briefs:
        market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
        vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
        rows.append(
            f"<a class='choose' href='{esc(fname)}'><b>{esc(data.get('topic'))}</b> "
            f"<span class='muted'>· {esc(market)} · {esc(vertical)}</span></a>"
        )
    body = (
        "<h1>D1 Market Intelligence — demo briefs</h1>"
        "<p class='sub'>Offline, obviously-fictional synthetic data. Local profile, no cloud.</p>"
        + "".join(rows)
    )
    return _page("D1 demo briefs", body)


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("scripts/out")
    briefs: list[tuple[str, dict[str, Any]]] = []
    for json_path in sorted(out_dir.glob("brief-*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        html_name = json_path.stem + ".html"
        (out_dir / html_name).write_text(render_brief(data), encoding="utf-8")
        briefs.append((html_name, data))
        print(f"wrote {out_dir / html_name}")
    (out_dir / "index.html").write_text(render_index(briefs), encoding="utf-8")
    print(f"wrote {out_dir / 'index.html'}  ({len(briefs)} brief(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
