"""On-prem placeholder for ``ResearchPort`` — the sovereign migration target.

A reversibility (no-lock-in) placeholder: in the managed profile this port binds to the
Gemini Deep Research adapter; switching ``profile`` to ``onprem`` rebinds it here. The
adapter constructs cleanly with **no external dependencies** and structurally satisfies the
same Protocol, so the contract tests prove interface parity. Porting D1 on-premise is only
a matter of filling these bodies in; the domain orchestration does not change.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CompetitorMove, Market, ResearchQuery, ResearchResult, Vertical

_MESSAGE = (
    "On-prem ResearchPort adapter is a migration placeholder; implement against your "
    "on-premise deep-research stack. Core domain logic is unchanged."
)


class OnPremResearchAdapter:
    """Placeholder research adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def research(self, query: ResearchQuery) -> ResearchResult:
        raise NotImplementedError(_MESSAGE)

    def competitor_snapshots(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]:
        raise NotImplementedError(_MESSAGE)
