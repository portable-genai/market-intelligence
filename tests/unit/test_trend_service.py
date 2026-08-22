"""Unit tests for the deterministic trend-scoring engine."""

from __future__ import annotations

from datetime import date

from market_intelligence.domain.models import (
    Citation,
    Market,
    SourceType,
    TrendDirection,
    TrendSignal,
    Vertical,
)
from market_intelligence.domain.trend_service import TrendScoringService

SVC = TrendScoringService()
AS_OF = date(2026, 6, 24)


def _sig(topic: str, day: str, weight: float = 1.0, sid: str = "s") -> TrendSignal:
    return TrendSignal(
        topic=topic,
        observed_date=day,
        weight=weight,
        citation=Citation(source_id=sid, source_type=SourceType.NEWS, title=sid),
    )


def test_no_signals_scores_zero_and_fading():
    ts = SVC.score("x", [], Market.SG, Vertical.BANKING, AS_OF)
    assert ts.score == 0.0
    assert ts.direction is TrendDirection.FADING
    assert ts.mentions == 0


def test_all_recent_mentions_score_high_and_rising():
    sigs = [_sig("bnpl", "2026-06-24", sid="a"), _sig("bnpl", "2026-06-20", sid="b")]
    ts = SVC.score("bnpl", sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert ts.score > 0.8
    assert ts.direction is TrendDirection.RISING
    assert ts.mentions == 2
    assert ts.distinct_sources == 2


def test_old_mentions_fade():
    sigs = [_sig("foo", "2025-01-01", sid="a")]
    ts = SVC.score("foo", sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert ts.score < 0.3
    assert ts.direction is TrendDirection.FADING


def test_only_matching_topic_counts():
    sigs = [_sig("a", "2026-06-24"), _sig("b", "2026-06-24")]
    ts = SVC.score("a", sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert ts.mentions == 1


def test_score_all_ranks_by_score_descending():
    sigs = [
        _sig("hot", "2026-06-24", sid="a"),
        _sig("cold", "2024-01-01", sid="b"),
    ]
    scores = SVC.score_all(sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert [s.topic for s in scores][0] == "hot"
    assert scores[0].score >= scores[-1].score


def test_determinism():
    sigs = [_sig("x", "2026-06-10"), _sig("x", "2026-05-10")]
    a = SVC.score("x", sigs, Market.SG, Vertical.BANKING, AS_OF)
    b = SVC.score("x", sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert a.score == b.score
    assert a.direction == b.direction


def test_mixed_sign_weights_never_break_the_zero_to_one_invariant():
    # A recent negative-weight signal plus an older positive one made the raw decayed/raw
    # ratio go negative; the score must still respect its documented 0..1 invariant.
    sigs = [
        _sig("x", "2026-06-24", weight=-2.0, sid="a"),
        _sig("x", "2020-01-01", weight=3.0, sid="b"),
    ]
    ts = SVC.score("x", sigs, Market.SG, Vertical.BANKING, AS_OF)
    assert 0.0 <= ts.score <= 1.0


def test_score_is_clamped_into_unit_interval_for_all_weights():
    for weights in ([-5.0, 1.0], [-1.0], [2.0, -3.0, 0.5], [0.0, 0.0]):
        sigs = [_sig("x", "2026-06-24", weight=w, sid=f"s{i}") for i, w in enumerate(weights)]
        ts = SVC.score("x", sigs, Market.SG, Vertical.BANKING, AS_OF)
        assert 0.0 <= ts.score <= 1.0, f"score {ts.score} out of range for weights {weights}"


def test_defaults():
    svc = TrendScoringService()
    assert svc.half_life_days == 30.0
    assert svc.rising_band == 0.6
