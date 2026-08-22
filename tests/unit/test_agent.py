"""Import-safety + wiring tests for the D1 ADK agent layer.

The local / on-prem / test profile installs **no Google Cloud SDK**, so importing the agent
wiring modules (and building the AgentCard, and calling the plain tool callables) must never
pull in ``google.adk`` / ``google-cloud-*``. The agent-card endpoint is also exercised
end-to-end against the local SDK-free stack via a monkeypatched in-memory container.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from market_intelligence.api import deps
from market_intelligence.api.app import app
from market_intelligence.config import Container, LocalSettings, Settings

CONFIG_PATH = "config/settings.yaml"

_EXPECTED_SKILLS = {"build_market_brief", "competitor_analysis"}


def _local_settings() -> Settings:
    base = Settings.load(CONFIG_PATH)
    return Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        grounding_enabled=base.grounding_enabled,
        models=base.models,
        deep_research=base.deep_research,
        knowledge_base=base.knowledge_base,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(db_path=":memory:", audit_path=":memory:"),
        markets=base.markets,
        adapters=base.adapters,
    )


# --------------------------------------------------------------------------- #
# Import safety (no ADK installed)
# --------------------------------------------------------------------------- #
def test_agent_package_imports_without_adk() -> None:
    module = importlib.import_module("market_intelligence.agent")
    assert module.build_root_agent is not None
    assert module.build_agent_card is not None
    assert "google.adk" not in sys.modules


def test_agent_root_imports_without_adk() -> None:
    module = importlib.import_module("market_intelligence.agent.root_agent")
    # Touching the lazy proxy's repr must not build the agent (would require ADK).
    assert repr(module.root_agent)
    assert "google.adk" not in sys.modules


def test_mcp_toolset_is_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    ra = importlib.import_module("market_intelligence.agent.root_agent")

    monkeypatch.delenv(ra.MCP_SERVER_URL_ENV, raising=False)
    assert ra._build_mcp_toolset() is None
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The AgentCard is pure domain (no ADK)
# --------------------------------------------------------------------------- #
def test_agent_card_is_pure() -> None:
    from market_intelligence.agent.agent_card import build_agent_card

    card = build_agent_card(_local_settings())
    assert card.name == "market-intelligence"
    assert {s.id for s in card.skills} == _EXPECTED_SKILLS


def test_governed_tools_match_card_skills() -> None:
    """Least privilege (R4): the tool surface and the advertised skills stay in step."""
    from market_intelligence.agent import tools
    from market_intelligence.agent.agent_card import SKILLS

    assert tools.governed_tool_names() == {s.id for s in SKILLS}


# --------------------------------------------------------------------------- #
# The plain tool callables run offline against the local stack (no ADK)
# --------------------------------------------------------------------------- #
def test_build_market_brief_tool_offline() -> None:
    from market_intelligence.agent.tools import build_market_brief

    result = build_market_brief(
        "savings and account fees",
        market="SG",
        vertical="banking",
        actor="analyst@brand.example",
        settings=_local_settings(),
    )
    assert result["requires_human_review"] is True
    assert result["citations"], "a brief must carry citations"
    assert "google.adk" not in sys.modules


def test_competitor_analysis_tool_offline() -> None:
    from market_intelligence.agent.tools import competitor_analysis

    result = competitor_analysis(
        "digital onboarding",
        market="SG",
        vertical="banking",
        actor="analyst@brand.example",
        settings=_local_settings(),
    )
    assert result["requires_human_review"] is True
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The agent-card endpoint end-to-end (local stack)
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    container = Container(_local_settings())
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_agent_card_endpoint(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "market-intelligence"
    assert {s["id"] for s in body["skills"]} == _EXPECTED_SKILLS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
