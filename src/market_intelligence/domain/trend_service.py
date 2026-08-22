"""TrendScoringService — deterministic trend scoring.

The third deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given dated, weighted signals (mentions of a topic, each with
provenance) it computes a normalised 0..1 momentum score and a direction (RISING / STEADY
/ FADING) using a transparent recency-weighted formula. The momentum that drives strategy
must be auditable, so it is code, not an LLM guess. The LLM only narrates the result.

Determinism: same inputs (including the ``as_of`` date passed in) -> same output. No clock
read inside the method (``as_of`` is a parameter), no randomness, no network. Tunables
(half-life, the rising/fading band) are fields, not magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import (
    Citation,
    Market,
    TrendDirection,
    TrendScore,
    TrendSignal,
    Vertical,
)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class TrendScoringService:
    """Pure, deterministic recency-weighted trend scoring.

    ``half_life_days`` controls how fast older mentions decay; ``rising_band`` /
    ``fading_band`` set the direction thresholds on the recent-vs-total momentum ratio.
    """

    half_life_days: float = 30.0
    recent_window_days: int = 30
    rising_band: float = 0.6
    fading_band: float = 0.3

    def score(
        self,
        topic: str,
        signals: tuple[TrendSignal, ...] | list[TrendSignal],
        market: Market,
        vertical: Vertical,
        as_of: date,
    ) -> TrendScore:
        """Compute a normalised momentum score for ``topic`` as of ``as_of``."""
        relevant = [s for s in signals if s.topic == topic]
        if not relevant:
            return TrendScore(
                topic=topic,
                market=market,
                vertical=vertical,
                score=0.0,
                direction=TrendDirection.FADING,
                mentions=0,
                distinct_sources=0,
                rationale="No signals for this topic in the window.",
            )

        decayed_total = 0.0
        recent_weight = 0.0
        raw_weight = 0.0
        citations: list[Citation] = []
        seen_sources: set[str] = set()
        for s in relevant:
            d = _parse_date(s.observed_date)
            age = (as_of - d).days if d is not None else self.recent_window_days * 4
            age = max(age, 0)
            decay = 0.5 ** (age / self.half_life_days)
            decayed_total += s.weight * decay
            raw_weight += s.weight
            if age <= self.recent_window_days:
                recent_weight += s.weight * decay
            if s.citation is not None:
                citations.append(s.citation)
                seen_sources.add(s.citation.source_id)

        score = self._normalise(decayed_total, raw_weight)
        momentum = (recent_weight / decayed_total) if decayed_total > 0 else 0.0
        direction = self._direction(momentum)
        rationale = (
            f"{len(relevant)} mention(s) across {len(seen_sources)} source(s); "
            f"recency-weighted score {score:.2f}, momentum {momentum:.2f} -> {direction.value}."
        )
        return TrendScore(
            topic=topic,
            market=market,
            vertical=vertical,
            score=round(score, 4),
            direction=direction,
            mentions=len(relevant),
            distinct_sources=len(seen_sources),
            rationale=rationale,
            citations=tuple(citations),
        )

    def score_all(
        self,
        signals: tuple[TrendSignal, ...] | list[TrendSignal],
        market: Market,
        vertical: Vertical,
        as_of: date,
    ) -> tuple[TrendScore, ...]:
        """Score every distinct topic, ranked by score descending then topic name."""
        topics = sorted({s.topic for s in signals})
        scores = [self.score(t, signals, market, vertical, as_of) for t in topics]
        scores.sort(key=lambda ts: (-ts.score, ts.topic))
        return tuple(scores)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise(decayed_total: float, raw_weight: float) -> float:
        """Map decayed weight into 0..1 via a saturating ratio against raw weight.

        A topic whose mentions are all recent approaches 1.0; one whose mentions are all
        old approaches 0.0. With no decay (all today) score == 1.0.

        The result is clamped to ``[0.0, 1.0]`` so the documented 0..1 score invariant
        holds even for pathological inputs (e.g. mixed-sign signal weights, where the raw
        ratio could otherwise fall below 0 or, with a negative ``raw_weight``, exceed 1).
        """
        if raw_weight <= 0:
            return 0.0
        return max(0.0, min(decayed_total / raw_weight, 1.0))

    def _direction(self, momentum: float) -> TrendDirection:
        if momentum >= self.rising_band:
            return TrendDirection.RISING
        if momentum <= self.fading_band:
            return TrendDirection.FADING
        return TrendDirection.STEADY
