"""SwotSynthesisService — deterministic SWOT + where-to-play synthesis.

The fourth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. From the competitor diff, the trend scores and the cited claims it
synthesises a SWOT and a ranked set of where-to-play options. The consequential strategy
math (which competitor moves are threats, which rising trends are opportunities, and the
attractiveness x right-to-win score that ranks options) is deterministic and unit-tested;
the LLM only narrates each item afterwards.

Determinism: same inputs -> same output. No LLM, no clock, no randomness, no network.
Weights and bands are tunable fields, not magic numbers. Every emitted item carries the
citations of the evidence it was derived from, so the SWOT is auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    Claim,
    CompetitorDiff,
    Market,
    MoveStatus,
    Severity,
    SwotItem,
    SwotKind,
    SwotSynthesis,
    TrendDirection,
    TrendScore,
    Vertical,
    WhereToPlayOption,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.75,
    Severity.MEDIUM: 0.5,
    Severity.LOW: 0.25,
}


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


@dataclass(frozen=True, slots=True)
class SwotSynthesisService:
    """Pure, deterministic SWOT + ranked where-to-play synthesis."""

    # Combine attractiveness and right-to-win into the option score (weights sum to 1).
    attractiveness_weight: float = 0.6
    right_to_win_weight: float = 0.4
    # A rising trend at or above this score becomes an OPPORTUNITY.
    opportunity_trend_score: float = 0.5
    max_options: int = 5

    def synthesize(
        self,
        market: Market,
        vertical: Vertical,
        diff: CompetitorDiff,
        trends: tuple[TrendScore, ...] | list[TrendScore],
        claims: tuple[Claim, ...] | list[Claim],
    ) -> SwotSynthesis:
        items: list[SwotItem] = []
        items.extend(self._threats_from_diff(diff))
        items.extend(self._opportunities_from_trends(trends))
        items.extend(self._from_claims(claims))
        items.sort(key=self._item_sort_key)

        options = self._where_to_play(market, vertical, diff, trends)
        return SwotSynthesis(market=market, vertical=vertical, items=tuple(items), options=options)

    # ------------------------------------------------------------------ #
    # SWOT derivation
    # ------------------------------------------------------------------ #
    def _threats_from_diff(self, diff: CompetitorDiff) -> list[SwotItem]:
        """A competitor's new / changed high-impact move is a THREAT."""
        out: list[SwotItem] = []
        for delta in diff.material_deltas:
            verb = {
                MoveStatus.NEW: "launched",
                MoveStatus.CHANGED: "changed",
                MoveStatus.WITHDRAWN: "withdrew",
            }.get(delta.status, "moved")
            out.append(
                SwotItem(
                    kind=SwotKind.THREAT,
                    statement=f"{delta.competitor} {verb}: {delta.summary}",
                    weight=_SEVERITY_WEIGHT[delta.severity],
                    citations=delta.citations,
                )
            )
        return out

    def _opportunities_from_trends(
        self, trends: tuple[TrendScore, ...] | list[TrendScore]
    ) -> list[SwotItem]:
        """A rising trend above the threshold is an OPPORTUNITY."""
        out: list[SwotItem] = []
        for t in trends:
            if t.direction is TrendDirection.RISING and t.score >= self.opportunity_trend_score:
                out.append(
                    SwotItem(
                        kind=SwotKind.OPPORTUNITY,
                        statement=f"Rising demand for {t.topic} (score {t.score:.2f}).",
                        weight=t.score,
                        citations=t.citations,
                    )
                )
        return out

    @staticmethod
    def _from_claims(claims: tuple[Claim, ...] | list[Claim]) -> list[SwotItem]:
        """Claims tagged with a strength/weakness keyword seed the internal SWOT axes.

        Generic and vertical-agnostic: the keyword is a transparent classifier, never an
        LLM call, so the SWOT stays replayable.
        """
        out: list[SwotItem] = []
        for claim in claims:
            lower = claim.text.lower()
            if "our strength" in lower or "we lead" in lower or "we are strong" in lower:
                out.append(
                    SwotItem(
                        kind=SwotKind.STRENGTH,
                        statement=claim.text,
                        weight=claim.confidence,
                        citations=claim.citations,
                    )
                )
            elif "our gap" in lower or "we lag" in lower or "we are weak" in lower:
                out.append(
                    SwotItem(
                        kind=SwotKind.WEAKNESS,
                        statement=claim.text,
                        weight=claim.confidence,
                        citations=claim.citations,
                    )
                )
        return out

    # ------------------------------------------------------------------ #
    # Where-to-play
    # ------------------------------------------------------------------ #
    def _where_to_play(
        self,
        market: Market,
        vertical: Vertical,
        diff: CompetitorDiff,
        trends: tuple[TrendScore, ...] | list[TrendScore],
    ) -> tuple[WhereToPlayOption, ...]:
        """Score one option per rising trend: attractiveness from the trend, right-to-win
        reduced where competitors are already crowding the same space.
        """
        # Count material competitor moves to gauge crowding (lowers right-to-win).
        crowding = len(diff.material_deltas)
        options: list[WhereToPlayOption] = []
        for t in trends:
            if t.direction is TrendDirection.FADING:
                continue
            attractiveness = t.score
            right_to_win = max(0.0, 1.0 - 0.1 * crowding)
            score = (
                self.attractiveness_weight * attractiveness
                + self.right_to_win_weight * right_to_win
            )
            options.append(
                WhereToPlayOption(
                    id=f"wtp:{_slug(t.topic)}",
                    title=f"Play in {t.topic}",
                    attractiveness=round(attractiveness, 4),
                    right_to_win=round(right_to_win, 4),
                    score=round(score, 4),
                    rationale=(
                        f"{t.direction.value} trend (score {t.score:.2f}); "
                        f"{crowding} material competitor move(s) in "
                        f"{market.value}/{vertical.value}."
                    ),
                    citations=t.citations,
                )
            )
        options.sort(key=lambda o: (-o.score, o.id))
        return tuple(options[: self.max_options])

    # ------------------------------------------------------------------ #
    # Ordering
    # ------------------------------------------------------------------ #
    @staticmethod
    def _item_sort_key(item: SwotItem) -> tuple[int, float, str]:
        kind_rank = {
            SwotKind.THREAT: 0,
            SwotKind.OPPORTUNITY: 1,
            SwotKind.STRENGTH: 2,
            SwotKind.WEAKNESS: 3,
        }
        return (kind_rank[item.kind], -item.weight, item.statement)
