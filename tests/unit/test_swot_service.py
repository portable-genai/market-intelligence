"""Unit tests for the deterministic SWOT / where-to-play synthesis engine."""

from __future__ import annotations

from market_intelligence.domain.models import (
    Citation,
    Claim,
    CompetitorDiff,
    Market,
    MoveDelta,
    MoveKind,
    MoveStatus,
    Severity,
    SourceType,
    SwotKind,
    TrendDirection,
    TrendScore,
    Vertical,
)
from market_intelligence.domain.swot_service import SwotSynthesisService

SVC = SwotSynthesisService()


def _delta(competitor: str, severity: Severity, status: MoveStatus = MoveStatus.NEW) -> MoveDelta:
    return MoveDelta(
        id=f"{competitor}:{status.value}",
        competitor=competitor,
        kind=MoveKind.RATE_CHANGE,
        status=status,
        summary="a move",
        severity=severity,
        citations=(Citation(source_id="c1", source_type=SourceType.WEB, title="c1"),),
    )


def _trend(topic: str, score: float, direction: TrendDirection) -> TrendScore:
    return TrendScore(
        topic=topic,
        market=Market.SG,
        vertical=Vertical.BANKING,
        score=score,
        direction=direction,
        citations=(Citation(source_id="t1", source_type=SourceType.NEWS, title="t1"),),
    )


def _diff(deltas: tuple[MoveDelta, ...]) -> CompetitorDiff:
    return CompetitorDiff(market=Market.SG, vertical=Vertical.BANKING, deltas=deltas)


def test_material_competitor_move_becomes_threat():
    diff = _diff((_delta("Acme", Severity.HIGH),))
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, (), ())
    threats = out.by_kind(SwotKind.THREAT)
    assert len(threats) == 1
    assert "Acme" in threats[0].statement


def test_rising_trend_becomes_opportunity():
    diff = _diff(())
    trends = (_trend("bnpl", 0.8, TrendDirection.RISING),)
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    opps = out.by_kind(SwotKind.OPPORTUNITY)
    assert len(opps) == 1
    assert "bnpl" in opps[0].statement


def test_fading_trend_is_not_an_opportunity_or_option():
    diff = _diff(())
    trends = (_trend("flip-phones", 0.1, TrendDirection.FADING),)
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    assert out.by_kind(SwotKind.OPPORTUNITY) == ()
    assert out.options == ()  # fading trends produce no where-to-play option


def test_strength_and_weakness_from_claims():
    diff = _diff(())
    claims = (
        Claim(text="Our strength is the branch network", subject="self", confidence=0.7),
        Claim(text="We lag on mobile onboarding", subject="self", confidence=0.6),
    )
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, (), claims)
    assert len(out.by_kind(SwotKind.STRENGTH)) == 1
    assert len(out.by_kind(SwotKind.WEAKNESS)) == 1


def test_where_to_play_ranked_and_score_blends_attractiveness_and_right_to_win():
    diff = _diff((_delta("Acme", Severity.HIGH),))  # one material move -> crowding 1
    trends = (
        _trend("high", 0.9, TrendDirection.RISING),
        _trend("low", 0.4, TrendDirection.STEADY),
    )
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    assert [o.title for o in out.options][0] == "Play in high"
    top = out.options[0]
    expected = round(0.6 * 0.9 + 0.4 * (1.0 - 0.1 * 1), 4)
    assert top.score == expected


def test_threats_rank_before_opportunities():
    diff = _diff((_delta("Acme", Severity.HIGH),))
    trends = (_trend("bnpl", 0.9, TrendDirection.RISING),)
    out = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    assert out.items[0].kind is SwotKind.THREAT


def test_determinism():
    diff = _diff((_delta("Acme", Severity.HIGH),))
    trends = (_trend("bnpl", 0.9, TrendDirection.RISING),)
    a = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    b = SVC.synthesize(Market.SG, Vertical.BANKING, diff, trends, ())
    assert [i.statement for i in a.items] == [i.statement for i in b.items]
    assert [o.id for o in a.options] == [o.id for o in b.options]


def test_defaults():
    svc = SwotSynthesisService()
    assert svc.attractiveness_weight == 0.6
    assert svc.right_to_win_weight == 0.4
