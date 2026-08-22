"""Wire-contract tests for the platform eval adapter (Hrz4 AI Quality / Model-Risk).

These pin the hardened Hrz4 contract the ``RemoteEvaluationAdapter`` must speak:

* ``evaluate`` POSTs a **structured** ``target`` plus a top-level ``dataset_id`` and a
  ``bundle`` to ``/v1/evaluations``; the top-level ``dataset_id`` equals ``target.dataset_id``;
  the body never carries a metric-name list; ``results[]`` parses into an ``EvalReport``.
* ``gate`` POSTs the same body shape to ``/v1/gate`` and returns the ``passed`` bool.

The response fixtures model the hardened ``agent-eval-kit`` contract, which is far stricter
than a naked aggregate boolean. The client RE-DERIVES every verdict from
the evidence and raises on any contradiction, on both paths: an evaluation response needs
durable identifiers (``run_id``, ``dataset_version``, ``dataset_digest``, ``evaluator``,
``schema_version``), a non-empty ``artifact_refs``, an ``attested`` flag, a positive
``n_examples``, and per-metric rows whose ``passed`` equals ``score >= threshold``; a gate
response needs all of that inside ``eval_report``, plus a ``redteam_report`` whose aggregate
matches its rows and whose every row's ``passed`` and ``blocked`` agree, durable
``model_card_ref`` and ``mrm_evidence_ref``, and a top-level ``passed`` equal to
(eval passed AND attested AND red-team passed).

The refusal tests are the point of the upgrade, not an inconvenience: a promotion certified
by a naked ``{"passed": true}`` is a promotion certified by nothing.

Every value is obviously fictional. HTTP is mocked with ``respx`` (a dev dependency); no
live Hrz4 is contacted.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from market_intelligence.adapters.platform.remote_evaluation import (
    RemoteEvaluationAdapter,
    RemoteEvaluationError,
)
from market_intelligence.config import Settings
from market_intelligence.domain.models import EvalReport

_BASE = "https://hrz4.test"
_DATASET = "data/golden/mkt-intel-suite.jsonl"
_DIGEST = "sha256:feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface"


def _evidence(**overrides: Any) -> dict[str, Any]:
    """Durable evaluation evidence in the full hardened shape, obviously fictional."""
    body: dict[str, Any] = {
        "n_examples": 24,
        "run_id": "run-fictional-0001",
        "dataset_version": "mkt-intel-suite@2026-08-01",
        "dataset_digest": _DIGEST,
        "evaluator": "hrz4-ai-quality (FICTIONAL)",
        "schema_version": "v1",
        "artifact_refs": ["gs://fictional-hrz4-evidence/run-fictional-0001/report.json"],
        "attested": True,
    }
    body.update(overrides)
    return body


#: A MIXED result set: citation_accuracy misses its bar, so the report FAILS. Every row is
#: internally consistent, because the client re-derives each verdict from score/threshold
#: and raises rather than trusting the flag.
_FAILING_RESULTS = [
    {"metric": "brief_groundedness", "score": 0.91, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.72, "threshold": 0.80, "passed": False},
]

_PASSING_RESULTS = [
    {"metric": "brief_groundedness", "score": 0.91, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.88, "threshold": 0.80, "passed": True},
]


def _gate_body(**overrides: Any) -> dict[str, Any]:
    """The complete GateDecision the promotion gate now demands."""
    body: dict[str, Any] = {
        "passed": True,
        "eval_report": _evidence(results=_PASSING_RESULTS),
        "redteam_report": {
            "passed": True,
            "results": [
                {"case": "prompt-injection-01", "passed": True, "blocked": True},
                {"case": "competitor-pii-exfil-01", "passed": True, "blocked": True},
            ],
        },
        "model_card_ref": "gs://fictional-hrz4-evidence/model-cards/mkt1-market-intel.md",
        "mrm_evidence_ref": "gs://fictional-hrz4-evidence/mrm/mkt1-market-intel-2026-08.json",
    }
    body.update(overrides)
    return body


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> RemoteEvaluationAdapter:
    monkeypatch.setenv("HRZ_QUALITY_URL", _BASE)
    return RemoteEvaluationAdapter(Settings())


@respx.mock
def test_evaluate_posts_hardened_body_and_parses_results(
    adapter: RemoteEvaluationAdapter,
) -> None:
    route = respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(results=_FAILING_RESULTS, passed=False))
    )

    report = adapter.evaluate(_DATASET)

    assert route.called
    sent = json.loads(route.calls.last.request.read())

    # Metrics are selected only by the bundle field — never a metric-name list.
    assert sent["bundle"] == "mkt1-market-intel"
    assert "metrics" not in sent
    assert "metric_names" not in sent

    # Structured target with the pinned reasoning model + prompt version.
    target = sent["target"]
    assert target["model"] == Settings().models.reasoning
    assert target["prompt_version"] == "v1"
    assert target["system"] == ""

    # dataset_id = basename without .jsonl, and top-level MUST equal target.dataset_id.
    assert target["dataset_id"] == "mkt-intel-suite"
    assert sent["dataset_id"] == target["dataset_id"]

    # results[] parsed into the domain EvalReport.
    assert isinstance(report, EvalReport)
    assert report.dataset == _DATASET
    assert [r.metric for r in report.results] == ["brief_groundedness", "citation_accuracy"]
    assert report.results[0].score == pytest.approx(0.91)
    assert report.results[0].passed is True
    assert report.n_examples == 24
    assert report.passed is False  # one metric failed

    # The attested evidence SURVIVES the adapter. A ``_to_domain`` mapper rebuilding the
    # report from dataset/results/n_examples drops every durable identifier the client had
    # just validated on the wire, so the adapter would throw away the exact evidence that
    # distinguishes a gated evaluation from a laptop one.
    assert report.run_id == "run-fictional-0001"
    assert report.dataset_version == "mkt-intel-suite@2026-08-01"
    assert report.dataset_digest == _DIGEST
    assert report.evaluator == "hrz4-ai-quality (FICTIONAL)"
    assert report.schema_version == "v1"
    assert report.artifact_refs == ("gs://fictional-hrz4-evidence/run-fictional-0001/report.json",)
    assert report.attested is True


@respx.mock
def test_evaluate_REFUSES_metric_rows_with_no_examples_behind_them(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """``all(())`` is vacuously true; a report that scored nothing must not parse."""
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(
            200, json=_evidence(results=_PASSING_RESULTS, n_examples=0, passed=True)
        )
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_evaluate_REFUSES_a_verdict_that_contradicts_its_score(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A row claiming PASS below its own threshold is evidence of a broken evaluator."""
    rows = [{"metric": "brief_groundedness", "score": 0.10, "threshold": 0.80, "passed": True}]
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(results=rows))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_evaluate_REFUSES_evidence_with_no_durable_identifiers(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """Without a run id or an artifact ref the score is unreproducible and unauditable."""
    body = _evidence(results=_PASSING_RESULTS, run_id="", artifact_refs=[])
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_gate_accepts_only_a_full_consistent_gate_decision(
    adapter: RemoteEvaluationAdapter,
) -> None:
    route = respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=_gate_body()))

    assert adapter.gate(_DATASET) is True
    assert route.called
    sent = json.loads(route.calls.last.request.read())
    assert route.calls.last.request.method == "POST"
    assert sent["bundle"] == "mkt1-market-intel"
    assert sent["dataset_id"] == sent["target"]["dataset_id"] == "mkt-intel-suite"
    assert "metrics" not in sent


@respx.mock
def test_gate_REFUSES_a_naked_boolean_with_no_evidence(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """The unhardened response shape. Accepting it is how a promotion gets certified by
    nothing, so the refusal is the contract."""
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json={"passed": True}))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_REFUSES_an_unattested_report_even_when_every_metric_passes(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A laptop evaluator can score the same corpus; that is not release authority."""
    body = _gate_body(eval_report=_evidence(results=_PASSING_RESULTS, attested=False))
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_REFUSES_a_redteam_aggregate_that_contradicts_its_rows(
    adapter: RemoteEvaluationAdapter,
) -> None:
    body = _gate_body(
        redteam_report={
            "passed": True,
            "results": [{"case": "prompt-injection-01", "passed": False, "blocked": False}],
        }
    )
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_returns_False_through_consistent_failing_evidence(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A FAIL still has to be a coherent story: a failing metric row, a failing report,
    and a top-level ``passed`` that agrees with both. A contradictory body raises."""
    body = _gate_body(passed=False, eval_report=_evidence(results=_FAILING_RESULTS))
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    assert adapter.gate(_DATASET) is False


@respx.mock
def test_non_2xx_raises_remote_evaluation_error(adapter: RemoteEvaluationAdapter) -> None:
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(422, text="unknown metric name")
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_transport_error_raises_remote_evaluation_error(
    adapter: RemoteEvaluationAdapter,
) -> None:
    respx.post(f"{_BASE}/v1/gate").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)
