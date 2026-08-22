"""API-boundary tests for server-side identity.

The FastAPI routes resolve a verified :class:`Principal` and pass ``actor=principal.actor``
into the domain service; a client cannot assert who they are. These assert:

* an unknown ``X-Dev-Persona`` is a hard 401 (no default fall-through to a valid identity),
* with no header the default persona's subject is the recorded audit actor, and
* a selected persona's subject is the recorded audit actor.

``deps.get_container`` is ``lru_cache``d, so we monkeypatch it to inject one in-memory
container (``:memory:`` SQLite) rather than mutating the environment.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from market_intelligence.api import deps
from market_intelligence.api.app import app
from market_intelligence.config import Container, LocalSettings, Settings

CONFIG_PATH = "config/settings.yaml"


def _container() -> Container:
    base = Settings.load(CONFIG_PATH)
    settings = Settings(
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
    return Container(settings)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    container = _container()
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


_BODY = {"topic": "savings and account fees", "market": "SG", "vertical": "banking"}


def _last_actor(container: Container) -> str:
    events = [e for e in container.audit.read_all() if e["action"] == "market_brief"]
    assert events, "expected a market_brief audit event"
    return str(events[-1]["actor"])


def test_unknown_persona_is_401(client: TestClient) -> None:
    res = client.post("/v1/brief", json=_BODY, headers={"X-Dev-Persona": "does-not-exist"})
    assert res.status_code == 401


def test_default_persona_is_the_audit_actor(client: TestClient) -> None:
    res = client.post("/v1/brief", json=_BODY)
    assert res.status_code == 200
    assert _last_actor(deps.get_container()) == "demo.analyst@brand.example"


def test_selected_persona_is_the_audit_actor(client: TestClient) -> None:
    res = client.post("/v1/brief", json=_BODY, headers={"X-Dev-Persona": "auditor"})
    assert res.status_code == 200
    assert _last_actor(deps.get_container()) == "demo.auditor@brand.example"


def test_personas_route_lists_seeded_personas(client: TestClient) -> None:
    res = client.get("/v1/personas")
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert {"analyst", "approver", "auditor", "other-tenant"} <= ids
