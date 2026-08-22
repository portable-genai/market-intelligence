"""Unit tests for config (vertical/market/region) and the local FTS5 knowledge base."""

from __future__ import annotations

from market_intelligence.adapters.local.knowledge_base import LocalKnowledgeBaseAdapter
from market_intelligence.config import Settings
from market_intelligence.domain.models import Market, RetrievalQuery, Vertical


def test_config_resolves_active_vertical_and_market(local_settings: Settings):
    assert local_settings.active_vertical is Vertical(local_settings.vertical)
    assert local_settings.active_market is Market(local_settings.market)


def test_market_profiles_carry_residency_regions(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).region == "asia-northeast1"
    assert local_settings.market_profile(Market.AU).region == "australia-southeast1"
    assert local_settings.market_profile(Market.SG).region == "asia-southeast1"


def test_jp_profile_is_bilingual(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).locales == ("ja", "en")


def test_env_overrides_select_vertical_and_market(monkeypatch):
    monkeypatch.setenv("MKT_VERTICAL", "online_retail")
    monkeypatch.setenv("MKT_MARKET", "JP")
    settings = Settings.load("config/settings.yaml")
    assert settings.active_vertical is Vertical.ONLINE_RETAIL
    assert settings.active_market is Market.JP


def test_local_kb_returns_scoped_cited_passages(local_settings: Settings):
    kb = LocalKnowledgeBaseAdapter(local_settings)
    passages = kb.search(
        RetrievalQuery(
            text="savings competitor move",
            market=Market.SG,
            vertical=Vertical.BANKING,
            top_k=5,
        )
    )
    assert passages, "local FTS5 corpus returned nothing for the seeded data"
    assert all(p.citation.page is not None for p in passages)
    for p in passages:
        assert "market:SG" in p.tags
        assert "vertical:banking" in p.tags


def test_local_kb_scope_excludes_other_market(local_settings: Settings):
    kb = LocalKnowledgeBaseAdapter(local_settings)
    sg = kb.search(
        RetrievalQuery(text="competitor", market=Market.SG, vertical=Vertical.BANKING, top_k=20)
    )
    assert all("market:SG" in p.tags for p in sg)
    assert all("market:AU" not in p.tags for p in sg)
