"""Service factories — build domain services from the DI container.

One place that wires the ports resolved by :class:`market_intelligence.config.Container`
into the domain orchestrator, so the CLI, API and agent layers share identical wiring.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import Container, Settings, build_container
from ..domain.dedup_service import ClaimDedupService
from ..domain.services import MarketBriefService
from ..domain.swot_service import SwotSynthesisService
from ..domain.trend_service import TrendScoringService


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()


def get_settings() -> Settings:
    """The active :class:`Settings` (the health endpoint reports the profile from here)."""
    return get_container().settings


def make_brief_service(container: Container | None = None) -> MarketBriefService:
    container = container or get_container()
    policy = container.settings.policy
    return MarketBriefService(
        research=container.research,
        knowledge_base=container.knowledge_base,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        dedup=ClaimDedupService(
            similarity_threshold=policy.claim_similarity_threshold,
            min_tokens=policy.claim_min_tokens,
        ),
        trend=TrendScoringService(
            half_life_days=policy.trend_half_life_days,
            recent_window_days=policy.trend_recent_window_days,
            rising_band=policy.trend_rising_band,
            fading_band=policy.trend_fading_band,
        ),
        swot=SwotSynthesisService(
            attractiveness_weight=policy.swot_attractiveness_weight,
            right_to_win_weight=policy.swot_right_to_win_weight,
            opportunity_trend_score=policy.swot_opportunity_trend_score,
            max_options=policy.swot_max_options,
        ),
        review_router=container.review_router,
    )
