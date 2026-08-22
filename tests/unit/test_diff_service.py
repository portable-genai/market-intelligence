"""Unit tests for the deterministic competitor-move diff engine."""

from __future__ import annotations

from market_intelligence.domain.diff_service import CompetitorDiffService
from market_intelligence.domain.models import (
    CompetitorMove,
    Market,
    MoveKind,
    MoveStatus,
    Severity,
    Vertical,
)


def _move(
    competitor: str,
    kind: MoveKind,
    summary: str,
    attrs: dict[str, str],
) -> CompetitorMove:
    return CompetitorMove(
        competitor=competitor,
        kind=kind,
        summary=summary,
        market=Market.SG,
        vertical=Vertical.BANKING,
        attributes=attrs,
    )


SVC = CompetitorDiffService()


def test_unchanged_when_snapshots_identical():
    move = _move("Acme", MoveKind.RATE_CHANGE, "Savings APR", {"apr": "4.0"})
    diff = SVC.diff((move,), (move,), Market.SG, Vertical.BANKING)
    assert all(d.status is MoveStatus.UNCHANGED for d in diff.deltas)
    assert diff.material_deltas == ()
    assert diff.requires_human_review is False


def test_new_move_detected():
    move = _move("Acme", MoveKind.PRODUCT_LAUNCH, "New card", {"apr": "0"})
    diff = SVC.diff((), (move,), Market.SG, Vertical.BANKING)
    assert len(diff.material_deltas) == 1
    assert diff.material_deltas[0].status is MoveStatus.NEW
    assert diff.material_deltas[0].severity is Severity.HIGH  # high-impact kind


def test_withdrawn_move_detected():
    move = _move("Acme", MoveKind.PROMOTION, "Sign-up bonus", {"bonus": "100"})
    diff = SVC.diff((move,), (), Market.SG, Vertical.BANKING)
    assert len(diff.material_deltas) == 1
    assert diff.material_deltas[0].status is MoveStatus.WITHDRAWN


def test_changed_attribute_detected_with_before_and_after():
    prev = _move("Acme", MoveKind.RATE_CHANGE, "Savings APR", {"apr": "3.8"})
    cur = _move("Acme", MoveKind.RATE_CHANGE, "Savings APR", {"apr": "4.1"})
    diff = SVC.diff((prev,), (cur,), Market.SG, Vertical.BANKING)
    delta = diff.material_deltas[0]
    assert delta.status is MoveStatus.CHANGED
    assert delta.changed_fields == ("apr",)
    assert delta.before == {"apr": "3.8"}
    assert delta.after == {"apr": "4.1"}
    assert delta.severity is Severity.HIGH  # rate change is high-impact


def test_severity_ranking_orders_high_before_medium():
    high = _move("Acme", MoveKind.RATE_CHANGE, "APR", {"apr": "1"})  # NEW high-impact -> HIGH
    medium = _move("Beta", MoveKind.PARTNERSHIP, "Tie-up", {"x": "1"})  # NEW other -> MEDIUM
    diff = SVC.diff((), (high, medium), Market.SG, Vertical.BANKING)
    severities = [d.severity for d in diff.deltas]
    assert severities[0] is Severity.HIGH
    assert severities[-1] is Severity.MEDIUM


def test_requires_human_review_on_high_severity():
    move = _move("Acme", MoveKind.RATE_CHANGE, "APR", {"apr": "1"})
    diff = SVC.diff((), (move,), Market.SG, Vertical.BANKING)
    assert diff.requires_human_review is True


def test_determinism():
    prev = _move("Acme", MoveKind.RATE_CHANGE, "APR", {"apr": "3.8"})
    cur = _move("Acme", MoveKind.RATE_CHANGE, "APR", {"apr": "4.1"})
    a = SVC.diff((prev,), (cur,), Market.SG, Vertical.BANKING)
    b = SVC.diff((prev,), (cur,), Market.SG, Vertical.BANKING)
    assert [d.id for d in a.deltas] == [d.id for d in b.deltas]
    assert [d.after for d in a.deltas] == [d.after for d in b.deltas]
