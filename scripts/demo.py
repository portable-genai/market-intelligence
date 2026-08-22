#!/usr/bin/env python3
"""Offline synthetic-data demo for D1 (audit-first).

Runs the real ``MarketBriefService`` over the local (offline) adapters for a few
(vertical, market) pairs, prints a readable, cited trace to stdout, and writes the brief
audit views to ``scripts/out/*.json`` for the dependency-free renderer / screenshots. It is
also the end-to-end smoke test for the slice: deterministic, so screenshots never drift.

Usage::

    MKT_INTEL_PROFILE=local python scripts/demo.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from market_intelligence.api.deps import make_brief_service
from market_intelligence.config import Container, LocalSettings, Settings
from market_intelligence.domain.models import BriefRequest, Market, Vertical
from market_intelligence.domain.serialization import to_jsonable
from market_intelligence.domain.services import MarketBriefService

_OUT = Path(__file__).resolve().parent / "out"
_AS_OF = date(2026, 6, 24)

_SCENARIOS = [
    ("savings and account fees", Market.SG, Vertical.BANKING),
    ("multi-currency wallets", Market.JP, Vertical.BANKING),
    ("loyalty programmes", Market.JP, Vertical.ONLINE_RETAIL),
    ("checkout payment options", Market.AU, Vertical.ONLINE_RETAIL),
]


def _service() -> MarketBriefService:
    base = Settings.load("config/settings.yaml")
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        grounding_enabled=base.grounding_enabled,
        models=base.models,
        deep_research=base.deep_research,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    return make_brief_service(Container(settings))


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    service = _service()
    for topic, market, vertical in _SCENARIOS:
        request = BriefRequest(topic=topic, market=market, vertical=vertical)
        brief = service.build_brief(request, actor="demo", as_of=_AS_OF)
        print("=" * 78)
        print(f"BRIEF: {topic}  [{market.value}/{vertical.value}]")
        print(f"  review required : {brief.requires_human_review}")
        print(f"  summary         : {brief.summary[:100]}...")
        if brief.competitor_analysis is not None:
            for d in brief.competitor_analysis.diff.material_deltas:
                print(f"  move [{d.severity.value}]: {d.competitor} {d.status.value} {d.summary}")
            for o in brief.competitor_analysis.swot.options:
                print(f"  play           : {o.title} (score {o.score:.2f})")
        print(f"  sources         : {len(brief.sources)}  citations: {len(brief.citations)}")
        out_path = _OUT / f"{brief.id}.json"
        out_path.write_text(json.dumps(to_jsonable(brief), indent=2), encoding="utf-8")
        print(f"  wrote           : {out_path}")
    print("=" * 78)
    print("Demo complete. Audit views written to scripts/out/ (obviously-fictional data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
