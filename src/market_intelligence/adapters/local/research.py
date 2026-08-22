"""Local research adapter (ResearchPort) — deterministic deep-research synthesizer.

The ``local`` profile's stand-in for the **Gemini Deep Research API + Grounding with
Google Search**: a deterministic, seedable synthesizer over the bundled fictional corpus
(``_seed.py``), with no model and no network. It returns cited sources and extracted
claims for the requested (topic, market, vertical), and the previous/current competitor
snapshots the deterministic diff engine compares. SDK-free and unconditional (there is no
emulator for Deep Research), and reproducible so the offline CLI and the unit tests agree.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import (
    CompetitorMove,
    Market,
    ResearchQuery,
    ResearchResult,
    Vertical,
)
from ._seed import COMPETITOR_SNAPSHOTS, RESEARCH_CLAIMS, RESEARCH_SOURCES


class LocalDeepResearchAdapter:
    """Deterministic deep-research synthesizer over the seeded fictional corpus."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def research(self, query: ResearchQuery) -> ResearchResult:
        key = (query.market, query.vertical)
        sources = RESEARCH_SOURCES.get(key, ())[: max(query.max_sources, 1)]
        claims = RESEARCH_CLAIMS.get(key, ())
        if query.competitors:
            wanted = {c.lower() for c in query.competitors}
            claims = tuple(
                c for c in claims if not c.subject or any(w in c.subject.lower() for w in wanted)
            )
        return ResearchResult(query=query, sources=tuple(sources), claims=tuple(claims))

    def competitor_snapshots(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]:
        previous, current = COMPETITOR_SNAPSHOTS.get((market, vertical), ((), ()))
        if competitors:
            wanted = {c.lower() for c in competitors}

            def keep(moves: tuple[CompetitorMove, ...]) -> tuple[CompetitorMove, ...]:
                return tuple(m for m in moves if any(w in m.competitor.lower() for w in wanted))

            previous, current = keep(previous), keep(current)
        return previous, current
