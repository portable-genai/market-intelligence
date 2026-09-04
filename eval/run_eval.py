#!/usr/bin/env python3
"""Offline evaluation gate for the D1 Market Intelligence system (A4).

This is the **promotion gate**: CI runs it on every change and the build fails if the
agent's market briefs fall below the model-risk thresholds agreed for a marketing-
intelligence agent (see ``eval/rubrics/*.yaml``)::

    brief_groundedness >= 0.80   (every brief carries citations on its claims)
    citation_accuracy  >= 0.90   (cites only retrieved / derived sources)
    diff_accuracy      >= 0.80   (the deterministic diff finds the expected moves)
    review_safety      >= 0.99   (every brief requires human review; maker-checker)

Two evaluators, one gate
------------------------
* **Production evaluator** — the **Gen AI evaluation service** on the Gemini Enterprise
  Agent Platform, wired in as ``EvaluationGatePort`` ->
  ``market_intelligence.adapters.gcp.genai_eval:GenAiEvalAdapter``. It needs GCP
  credentials. Select it with ``--use-gcp``.

* **Offline evaluator (default)** — a deterministic gate in this file. It needs **no GCP
  credentials and no Google Cloud SDK**, runs the real ``MarketBriefService`` against the
  local (offline) adapters over the golden set, and computes the four metrics. This is what
  guards the merge in CI.

Usage::

    python eval/run_eval.py                      # offline gate (CI)
    python eval/run_eval.py --dataset path.jsonl # custom golden set
    python eval/run_eval.py --use-gcp            # route through GenAiEvalAdapter

Exit code is ``0`` iff ``EvalReport.passed`` (every metric meets its threshold).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Domain models / config are pure-stdlib + the local adapters are SDK-free, so this script
# runs in the local / on-prem / test profile with no Google Cloud SDK installed.
# The --mode smoke|gate scaffold + aligned report rendering come from the shared
# agent-eval-kit commons; this script keeps only its own offline
# evaluator and gate runner.
from agent_eval_kit import assert_each_can_go_red, eval_main

from market_intelligence.domain.models import (
    BriefRequest,
    EvalMetricResult,
    EvalReport,
    Market,
    MarketBrief,
    Vertical,
)

THRESHOLDS: dict[str, float] = {
    "brief_groundedness": 0.80,
    "citation_accuracy": 0.90,
    "diff_accuracy": 0.80,
    "review_safety": 0.99,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_briefs.jsonl"
_AS_OF = date(2026, 6, 24)  # fixed clock so the eval is reproducible
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


# --------------------------------------------------------------------------- #
# Golden dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class GoldenExample:
    id: str
    topic: str
    market: str
    vertical: str
    expected_material_moves: int
    expected_requires_human_review: bool


def load_golden(path: Path) -> list[GoldenExample]:
    examples: list[GoldenExample] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        examples.append(
            GoldenExample(
                id=str(obj.get("id", f"example-{lineno}")),
                topic=str(obj["topic"]),
                market=str(obj["market"]),
                vertical=str(obj["vertical"]),
                expected_material_moves=int(obj.get("expected_material_moves", 0)),
                expected_requires_human_review=bool(obj["expected_requires_human_review"]),
            )
        )
    if not examples:
        raise SystemExit(f"{path}: golden dataset is empty")
    return examples


def load_thresholds_from_rubrics() -> dict[str, float]:
    """Read thresholds from ``eval/rubrics/*.yaml`` when PyYAML is available."""
    thresholds = dict(THRESHOLDS)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return thresholds
    rubric_dir = _REPO_ROOT / "eval" / "rubrics"
    for name in ("groundedness.yaml", "diff_accuracy.yaml"):
        rubric_path = rubric_dir / name
        if not rubric_path.exists():
            continue
        doc = yaml.safe_load(rubric_path.read_text(encoding="utf-8")) or {}
        metric = doc.get("metric")
        if isinstance(metric, str) and "threshold" in doc:
            thresholds[metric] = float(doc["threshold"])
        for companion, spec in (doc.get("companion_metrics") or {}).items():
            if isinstance(spec, dict) and "threshold" in spec:
                thresholds[str(companion)] = float(spec["threshold"])
    return thresholds


# --------------------------------------------------------------------------- #
# Service wiring (the real MarketBriefService over the local offline adapters)
# --------------------------------------------------------------------------- #
def _make_service():  # type: ignore[no-untyped-def]
    from market_intelligence.api.deps import make_brief_service
    from market_intelligence.config import LocalSettings, Settings

    base = Settings.load(str(_REPO_ROOT / "config" / "settings.yaml"))
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

    from market_intelligence.config import Container

    container = Container(settings)
    return make_brief_service(container)


# --------------------------------------------------------------------------- #
# Heuristic scorers
# --------------------------------------------------------------------------- #
def _claim_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if len(s.strip()) >= 12]


def score_groundedness(brief: MarketBrief) -> float:
    """Every brief with narrative claims must carry at least one citation."""
    if not _claim_sentences(brief.summary):
        return 1.0
    return 1.0 if brief.citations else 0.0


def score_citation_accuracy(brief: MarketBrief) -> float:
    """No cited source outside the brief's own retrieved / derived evidence set."""
    cited = {c.source_id for c in brief.citations}
    if not cited:
        return 1.0 if not _claim_sentences(brief.summary) else 0.0
    allowed: set[str] = {s.id for s in brief.sources}
    for claim in brief.key_claims:
        allowed.update(c.source_id for c in claim.citations)
    if brief.competitor_analysis is not None:
        for d in brief.competitor_analysis.diff.deltas:
            allowed.update(c.source_id for c in d.citations)
        for item in brief.competitor_analysis.swot.items:
            allowed.update(c.source_id for c in item.citations)
    return round(len(cited & allowed) / len(cited), 4)


def score_diff_accuracy(brief: MarketBrief, expected_moves: int) -> float:
    if brief.competitor_analysis is None:
        return 0.0
    actual = len(brief.competitor_analysis.diff.material_deltas)
    return 1.0 if actual == expected_moves else 0.0


def score_review_safety(brief: MarketBrief, expected_requires_review: bool) -> float:
    """Compare with the golden maker-checker oracle, never with the output itself."""
    return 1.0 if brief.requires_human_review is expected_requires_review else 0.0


def assert_review_safety_can_go_red(threshold: float) -> None:
    """Reject a future tautological safety scorer before trusting a green gate."""
    from types import SimpleNamespace

    assert_each_can_go_red(
        lambda brief: score_review_safety(brief, True),
        {
            "maker-checker": (
                SimpleNamespace(requires_human_review=True),
                SimpleNamespace(requires_human_review=False),
            )
        },
        threshold=threshold,
        metric="review_safety",
    )


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass
class _PerMetric:
    scores: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0


def run_offline(dataset: Path, thresholds: dict[str, float]) -> EvalReport:
    assert_review_safety_can_go_red(thresholds["review_safety"])
    examples = load_golden(dataset)
    service = _make_service()
    agg: dict[str, _PerMetric] = {m: _PerMetric() for m in THRESHOLDS}
    print(f"Running offline eval gate over {len(examples)} golden briefs (MarketBriefService).\n")
    for ex in examples:
        request = BriefRequest(
            topic=ex.topic, market=Market(ex.market), vertical=Vertical(ex.vertical)
        )
        brief = service.build_brief(request, actor="eval-bot", as_of=_AS_OF)
        agg["brief_groundedness"].scores.append(score_groundedness(brief))
        agg["citation_accuracy"].scores.append(score_citation_accuracy(brief))
        agg["diff_accuracy"].scores.append(score_diff_accuracy(brief, ex.expected_material_moves))
        agg["review_safety"].scores.append(
            score_review_safety(brief, ex.expected_requires_human_review)
        )

    order = ("brief_groundedness", "citation_accuracy", "diff_accuracy", "review_safety")
    results = tuple(
        EvalMetricResult(
            metric=metric,
            score=round(agg[metric].mean, 4),
            threshold=thresholds.get(metric, THRESHOLDS[metric]),
            passed=round(agg[metric].mean, 4) >= thresholds.get(metric, THRESHOLDS[metric]),
        )
        for metric in order
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(examples))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    """Promotion verdict via EvaluationGatePort (platform = model-quality-gate, gcp = Gen AI evals).

    Fails closed on the reconciled evaluate + gate result. Refuses to run outside the
    platform/gcp profiles so the offline smoke result is never relabelled a promotion pass.
    """
    from market_intelligence.config import Settings, build_container

    settings = Settings.load()
    if settings.profile not in ("platform", "gcp"):
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            "MKT_INTEL_PROFILE=platform or gcp "
            f"(got {settings.profile!r}); run --mode smoke for the offline pre-merge check."
        )
    container = build_container(settings)
    gate = container.evaluation
    report = gate.evaluate(str(dataset))
    if not isinstance(report, EvalReport):  # pragma: no cover - defensive
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    gate_passed = bool(gate.gate(str(dataset)))
    return report, gate_passed


def main(argv: list[str] | None = None) -> int:
    """Dispatch --mode via the shared eval_main scaffold (fail-closed exit codes).

    ``--use-gcp`` (the pre-split flag for the production evaluator) is kept as an alias
    for ``--mode gate``.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if "--use-gcp" in args:
        args = [a for a in args if a != "--use-gcp"] + ["--mode", "gate"]
    return eval_main(
        smoke=lambda dataset: run_offline(dataset, load_thresholds_from_rubrics()),
        gate=run_gate,
        default_dataset=DEFAULT_DATASET,
        description="Offline / platform evaluation gate for D1 (A4 / P-08).",
        smoke_label="offline heuristic (no GCP creds)",
        gate_label="promotion gate (EvaluationGatePort: model-quality-gate / Gen AI evals)",
        argv=args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
