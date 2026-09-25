"""The laptop ``live`` profile: Gemini research and narration, everything else local.

Owner rule (2026-09-23): an app whose use case needs an online search tool runs its model
calls on Gemini under ``live``. So under ``live`` the research port is Gemini grounded with
Google Search and the ``llm`` port is Gemini; every other port is the local adapter, and the
posture is the laptop posture ``local`` has.

The property a laptop demo depends on is that missing Gemini credentials do not stop the app:
it starts, serves its health and persona routes, and the research leg answers each request
with a plain 503 naming what is missing. Everything here runs offline, with no Google SDK
installed and no network: the unavailable paths are driven through a fake delegate.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER, _settings

from market_intelligence.adapters.live.research import LiveGroundedResearchAdapter
from market_intelligence.api import app as app_module
from market_intelligence.api import deps
from market_intelligence.config import (
    LAPTOP_PROFILES,
    RUNTIME_PROFILES,
    Container,
    Settings,
    resolve_profile,
)
from market_intelligence.domain.errors import ResearchUnavailableError
from market_intelligence.domain.models import Market, ResearchQuery, Vertical

CONFIG_PATH = "config/settings.yaml"

#: The two ports that leave the local family under ``live``, and where they go.
_GEMINI_BINDINGS = {
    "research": "market_intelligence.adapters.live.research:LiveGroundedResearchAdapter",
    "llm": "market_intelligence.adapters.gcp.gemini_llm:GeminiLLMAdapter",
}

_BODY = {"topic": "savings and account fees", "market": "SG", "vertical": "banking"}
_QUERY = ResearchQuery(
    topic="savings and account fees", market=Market.SG, vertical=Vertical.BANKING
)


def _live(**changes: object) -> Settings:
    """A ``live`` Settings with a named project, so only what a test changes is missing."""
    fields: dict[str, object] = {"project_id": "demo-project", **changes}
    return dataclasses.replace(_settings("live"), **fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Bindings and the container
# --------------------------------------------------------------------------- #
def test_live_is_a_runtime_profile_with_the_laptop_posture() -> None:
    assert "live" in RUNTIME_PROFILES
    assert {"local", "live"} == LAPTOP_PROFILES
    assert resolve_profile({"MKT_INTEL_PROFILE": "live"}).profile == "live"


def test_only_research_and_llm_leave_the_local_family_under_live() -> None:
    adapters = Settings.load(CONFIG_PATH).adapters
    for port, binding in adapters.items():
        expected = _GEMINI_BINDINGS.get(port, binding["local"])
        assert binding["live"] == expected, f"port {port!r} binds {binding['live']!r} under live"


def test_the_container_builds_every_port_under_live() -> None:
    """Every port constructs under ``live`` with no Google SDK and no credentials."""
    container = Container(_settings("live"))
    ports = [name for name in Settings.load(CONFIG_PATH).adapters]
    built = {port: getattr(container, port) for port in ports}
    assert all(adapter is not None for adapter in built.values())
    assert isinstance(built["research"], LiveGroundedResearchAdapter)
    assert type(built["llm"]).__name__ == "GeminiLLMAdapter"
    assert type(built["knowledge_base"]).__module__.startswith("market_intelligence.adapters.local")


# --------------------------------------------------------------------------- #
# Posture
# --------------------------------------------------------------------------- #
def test_live_binds_loopback_and_runs_on_the_laptop() -> None:
    settings = Settings(profile="live")
    assert settings.bind_profile == "local", "live serves seeded personas and must stay on loopback"
    assert settings.laptop_posture is True
    assert settings.runtime == "local"


def test_an_unconsented_run_is_never_the_laptop_posture() -> None:
    assert Settings(profile="live", profile_explicit=False).laptop_posture is False
    assert Settings(profile="local", profile_explicit=False).laptop_posture is False
    assert Settings(profile="gcp").laptop_posture is False


def test_the_model_pill_names_the_gemini_model_that_answers_under_live() -> None:
    settings = dataclasses.replace(Settings.load(CONFIG_PATH), profile="live")
    assert settings.generator_model == settings.models.reasoning
    assert settings.generator_model.startswith("gemini-")


def test_live_serves_the_seeded_personas() -> None:
    identity = Container(_settings("live")).identity
    assert identity.personas(), "the live persona picker needs the seeded personas"


def _origins(monkeypatch: pytest.MonkeyPatch, profile: str, *, explicit: bool) -> list[str]:
    monkeypatch.delenv("MKT_INTEL_CORS_ORIGINS", raising=False)
    settings = dataclasses.replace(
        app_module.deps.get_settings(), profile=profile, profile_explicit=explicit
    )
    monkeypatch.setattr(app_module.deps, "get_settings", lambda: settings)
    return app_module._cors_origins()


def test_live_gets_the_cors_dev_origins_only_when_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _origins(monkeypatch, "live", explicit=True) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert _origins(monkeypatch, "live", explicit=False) == []


# --------------------------------------------------------------------------- #
# The research leg reports itself unavailable, plainly
# --------------------------------------------------------------------------- #
class _Raising:
    """A delegate standing in for the Gemini adapter: every call raises ``exc``."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def research(self, query: ResearchQuery) -> object:
        raise self._exc

    def competitor_snapshots(self, *args: object) -> object:
        raise self._exc


def _adapter(settings: Settings, exc: BaseException) -> LiveGroundedResearchAdapter:
    adapter = LiveGroundedResearchAdapter(settings)
    adapter._delegate = _Raising(exc)  # type: ignore[assignment]
    return adapter


def _sdk_error(module: str, name: str, **attrs: object) -> BaseException:
    """An exception whose class is defined under ``module``, as the SDK's would be."""
    klass = type(name, (Exception,), {"__module__": module})
    exc = klass("simulated")
    for key, value in attrs.items():
        setattr(exc, key, value)
    return exc


def test_no_project_is_unavailable_before_any_call() -> None:
    adapter = _adapter(_live(project_id="your-gcp-project"), AssertionError("must not be called"))
    with pytest.raises(ResearchUnavailableError, match="GOOGLE_CLOUD_PROJECT"):
        adapter.research(_QUERY)


def test_grounding_switched_off_is_unavailable() -> None:
    adapter = _adapter(_live(grounding_enabled=False), AssertionError("must not be called"))
    with pytest.raises(ResearchUnavailableError, match="MKT_GROUNDING_ENABLED"):
        adapter.research(_QUERY)


def test_a_missing_client_library_names_the_live_extra() -> None:
    adapter = _adapter(_live(), ImportError("No module named 'google'"))
    with pytest.raises(ResearchUnavailableError, match=r"\[live\]"):
        adapter.research(_QUERY)


def test_missing_credentials_name_the_login_command() -> None:
    exc = _sdk_error("google.auth.exceptions", "DefaultCredentialsError")
    adapter = _adapter(_live(), exc)
    with pytest.raises(ResearchUnavailableError, match="application-default login"):
        adapter.competitor_snapshots(Market.SG, Vertical.BANKING, ())


def test_refused_credentials_are_unavailable_but_a_bad_request_is_not() -> None:
    refused = _sdk_error("google.genai.errors", "ClientError", code=403)
    with pytest.raises(ResearchUnavailableError, match="refused the credentials"):
        _adapter(_live(), refused).research(_QUERY)
    bad_request = _sdk_error("google.genai.errors", "ClientError", code=400)
    with pytest.raises(type(bad_request)):
        _adapter(_live(), bad_request).research(_QUERY)


def test_an_unrelated_failure_is_not_disguised_as_unavailable() -> None:
    with pytest.raises(ValueError):
        _adapter(_live(), ValueError("a real defect")).research(_QUERY)


def test_grounding_switch_parses_false_as_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """The settings value is interpolated TEXT, and the string "false" is truthy."""
    monkeypatch.setenv("MKT_INTEL_PROFILE", "live")
    monkeypatch.setenv("MKT_GROUNDING_ENABLED", "false")
    assert Settings.load(CONFIG_PATH).grounding_enabled is False
    monkeypatch.setenv("MKT_GROUNDING_ENABLED", "perhaps")
    with pytest.raises(ValueError, match="MKT_GROUNDING_ENABLED"):
        Settings.load(CONFIG_PATH)


# --------------------------------------------------------------------------- #
# The app starts without credentials and answers a plain 503
# --------------------------------------------------------------------------- #
@pytest.fixture
def live_client_without_credentials(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    container = Container(dataclasses.replace(_settings("live"), project_id="your-gcp-project"))
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app_module.app, client=LOOPBACK_PEER)


def test_the_app_starts_and_reports_live(live_client_without_credentials: TestClient) -> None:
    health = live_client_without_credentials.get("/healthz")
    assert health.status_code == 200
    body = health.json()
    assert body["profile"] == "live"
    assert body["runtime"] == "local"
    assert body["generator_model"].startswith("gemini-")
    assert live_client_without_credentials.get("/v1/personas").json()


@pytest.mark.parametrize("route", ["/v1/brief", "/v1/competitor-analysis"])
def test_research_without_credentials_is_a_plain_503(
    live_client_without_credentials: TestClient, route: str
) -> None:
    response = live_client_without_credentials.post(route, json=_BODY)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail.startswith("research unavailable:")
    assert "GOOGLE_CLOUD_PROJECT" in detail
