"""Domain services aggregator — one import surface for the wiring layers.

The API, CLI and agent layers import services from here so that adding or renaming a
service is a single-file change at the boundary. The orchestrator (:class:`MarketBriefService`)
composes the four deterministic engines and the ports.
"""

from __future__ import annotations

from .brief_service import MarketBriefService
from .dedup_service import ClaimDedupService
from .diff_service import CompetitorDiffService
from .swot_service import SwotSynthesisService
from .trend_service import TrendScoringService

__all__ = [
    "MarketBriefService",
    "ClaimDedupService",
    "CompetitorDiffService",
    "TrendScoringService",
    "SwotSynthesisService",
]
