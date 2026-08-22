from market_intelligence.domain import kernel, models


def test_kernel_is_stable_and_excludes_vertical_aggregates() -> None:
    assert models.ThinkingLevel is kernel.ThinkingLevel
    assert {"MarketBrief", "CompetitorAnalysis", "TrendScore"}.isdisjoint(kernel.__all__)
