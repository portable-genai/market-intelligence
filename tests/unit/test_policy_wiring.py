from types import SimpleNamespace

import pytest

from market_intelligence.api.deps import make_brief_service
from market_intelligence.config import PolicySettings


def test_adopter_policy_overrides_are_wired_into_deterministic_engines() -> None:
    marker = object()
    container = SimpleNamespace(
        settings=SimpleNamespace(
            policy=PolicySettings(
                claim_similarity_threshold=0.81,
                trend_half_life_days=7.0,
                trend_rising_band=0.8,
                trend_fading_band=0.2,
                swot_max_options=2,
            )
        ),
        research=marker,
        knowledge_base=marker,
        llm=marker,
        guardrail=marker,
        tracer=marker,
        audit=marker,
        review_router=None,
    )
    service = make_brief_service(container)
    assert service._dedup.similarity_threshold == 0.81
    assert service._trend.half_life_days == 7.0
    assert service._trend.rising_band == 0.8
    assert service._swot.max_options == 2


@pytest.mark.parametrize(
    "values",
    [
        {"swot_attractiveness_weight": -0.1, "swot_right_to_win_weight": 1.1},
        {"swot_opportunity_trend_score": 1.1},
        {"swot_attractiveness_weight": 0.7, "swot_right_to_win_weight": 0.4},
    ],
)
def test_invalid_swot_policy_is_refused(values: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="SWOT"):
        PolicySettings(**values)
