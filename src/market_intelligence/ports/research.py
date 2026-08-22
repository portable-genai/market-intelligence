"""ResearchPort — deep research / web grounding plus competitor snapshots.

Primary GCP adapter: the **Gemini Deep Research API** with Grounding with Google Search,
isolated so web egress stays in the grounding sub-agent. The port returns raw research
(sources + extracted claims) and the previous/current competitor-move snapshots that the
deterministic diff engine compares; it never synthesises the brief itself.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import (
    CompetitorMove,
    Market,
    ResearchQuery,
    ResearchResult,
    Vertical,
)


@runtime_checkable
class ResearchPort(Protocol):
    def research(self, query: ResearchQuery) -> ResearchResult:
        """Run deep research for ``query`` and return cited sources + extracted claims."""
        ...

    def competitor_snapshots(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]:
        """Return the (previous, current) competitor-move snapshots for the diff engine."""
        ...
