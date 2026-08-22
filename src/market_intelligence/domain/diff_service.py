"""CompetitorDiffService — deterministic competitor-move diff.

The second deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given a previous and a current snapshot of competitor moves, it
computes a stable, severity-ranked diff: which moves are NEW, which CHANGED (and exactly
which tracked attributes moved), and which were WITHDRAWN. This is the consequential
"what changed since last time" comparison an auditor must be able to re-run, so it is code,
not an LLM call. The LLM only narrates the resulting diff afterwards.

Determinism: same inputs -> same output. Moves are matched by a stable identity key
(competitor + kind + a slug of the summary); attribute changes are compared field by field;
severity is assigned by transparent rules (new/withdrawn and rate/fee/pricing moves rank
higher). Deltas are ordered by (severity desc, status, id) so the output never drifts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dedup_service import ClaimDedupService
from .models import (
    CompetitorDiff,
    CompetitorMove,
    Market,
    MoveDelta,
    MoveKind,
    MoveStatus,
    Severity,
    Vertical,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SEVERITY_RANK = {
    Severity.CRITICAL: 3,
    Severity.HIGH: 2,
    Severity.MEDIUM: 1,
    Severity.LOW: 0,
}
_STATUS_RANK = {
    MoveStatus.NEW: 0,
    MoveStatus.CHANGED: 1,
    MoveStatus.WITHDRAWN: 2,
    MoveStatus.UNCHANGED: 3,
}
# Move kinds whose appearance/withdrawal materially shifts the competitive picture.
_HIGH_IMPACT_KINDS = frozenset(
    {MoveKind.RATE_CHANGE, MoveKind.FEE_CHANGE, MoveKind.PRICING_CHANGE, MoveKind.PRODUCT_LAUNCH}
)


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


@dataclass(frozen=True, slots=True)
class CompetitorDiffService:
    """Pure, deterministic competitor-move diff with severity-ranked deltas."""

    def diff(
        self,
        previous: tuple[CompetitorMove, ...] | list[CompetitorMove],
        current: tuple[CompetitorMove, ...] | list[CompetitorMove],
        market: Market,
        vertical: Vertical,
    ) -> CompetitorDiff:
        prev_by_id = {self._move_id(m): m for m in previous}
        cur_by_id = {self._move_id(m): m for m in current}

        deltas: list[MoveDelta] = []
        for move_id, cur in cur_by_id.items():
            prev = prev_by_id.get(move_id)
            if prev is None:
                deltas.append(self._new_delta(move_id, cur))
            else:
                deltas.append(self._compare(move_id, prev, cur))
        for move_id, prev in prev_by_id.items():
            if move_id not in cur_by_id:
                deltas.append(self._withdrawn_delta(move_id, prev))

        deltas.sort(key=self._sort_key)
        return CompetitorDiff(market=market, vertical=vertical, deltas=tuple(deltas))

    # ------------------------------------------------------------------ #
    # Delta construction
    # ------------------------------------------------------------------ #
    def _new_delta(self, move_id: str, move: CompetitorMove) -> MoveDelta:
        return MoveDelta(
            id=move_id,
            competitor=move.competitor,
            kind=move.kind,
            status=MoveStatus.NEW,
            summary=move.summary,
            changed_fields=tuple(sorted(move.attributes)),
            before={},
            after=dict(move.attributes),
            severity=self._severity(MoveStatus.NEW, move.kind, ()),
            citations=move.citations,
        )

    def _withdrawn_delta(self, move_id: str, move: CompetitorMove) -> MoveDelta:
        return MoveDelta(
            id=move_id,
            competitor=move.competitor,
            kind=move.kind,
            status=MoveStatus.WITHDRAWN,
            summary=move.summary,
            changed_fields=tuple(sorted(move.attributes)),
            before=dict(move.attributes),
            after={},
            severity=self._severity(MoveStatus.WITHDRAWN, move.kind, ()),
            citations=move.citations,
        )

    def _compare(self, move_id: str, prev: CompetitorMove, cur: CompetitorMove) -> MoveDelta:
        changed = tuple(
            sorted(
                k
                for k in set(prev.attributes) | set(cur.attributes)
                if prev.attributes.get(k) != cur.attributes.get(k)
            )
        )
        status = MoveStatus.CHANGED if changed else MoveStatus.UNCHANGED
        # On a change, cite both the prior and current evidence (de-duplicated).
        citations = (
            ClaimDedupService.merge_citations(prev.citations + cur.citations)
            if changed
            else cur.citations
        )
        return MoveDelta(
            id=move_id,
            competitor=cur.competitor,
            kind=cur.kind,
            status=status,
            summary=cur.summary,
            changed_fields=changed,
            before={k: prev.attributes.get(k, "") for k in changed},
            after={k: cur.attributes.get(k, "") for k in changed},
            severity=self._severity(status, cur.kind, changed),
            citations=citations,
        )

    # ------------------------------------------------------------------ #
    # Severity / identity / ordering
    # ------------------------------------------------------------------ #
    @staticmethod
    def _severity(status: MoveStatus, kind: MoveKind, changed_fields: tuple[str, ...]) -> Severity:
        if status is MoveStatus.UNCHANGED:
            return Severity.LOW
        high_impact = kind in _HIGH_IMPACT_KINDS
        if status in (MoveStatus.NEW, MoveStatus.WITHDRAWN):
            return Severity.HIGH if high_impact else Severity.MEDIUM
        # CHANGED: many moved fields, or a high-impact kind, is more material.
        if high_impact or len(changed_fields) >= 2:
            return Severity.HIGH
        return Severity.MEDIUM

    @staticmethod
    def _move_id(move: CompetitorMove) -> str:
        return f"{_slug(move.competitor)}:{move.kind.value}:{_slug(move.summary)}"

    @staticmethod
    def _sort_key(delta: MoveDelta) -> tuple[int, int, str]:
        # Severity descending (negate rank), then status order, then id for stability.
        return (-_SEVERITY_RANK[delta.severity], _STATUS_RANK[delta.status], delta.id)
