"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

The Gemini adapters are driven here through a FAKE ``google.genai`` module, so what is proved is
this repository's half: the model id each call notes, whether it notes a search (only the
grounded research calls, which attach the ``google_search`` tool), and the sampling each call
sends. Sampling is decided per call: the grounded research and the File Search retrieval are
structured extraction the deterministic engines consume and compare, so they are PINNED at 0.0;
narration over the computed result is drafting, so it is FREE, which means no temperature is
sent at all (some models reject the parameter).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance
from tests.conftest import LOOPBACK_PEER, _settings

from market_intelligence import config
from market_intelligence.adapters.gcp.deep_research import GeminiDeepResearchAdapter
from market_intelligence.adapters.gcp.file_search_kb import FileSearchKnowledgeBaseAdapter
from market_intelligence.adapters.gcp.gemini_llm import GeminiLLMAdapter
from market_intelligence.adapters.local.llm import STUB_MODEL
from market_intelligence.api import deps
from market_intelligence.api.app import app
from market_intelligence.config import Container, Settings
from market_intelligence.domain.models import (
    LlmMessage,
    LlmRequest,
    Market,
    ResearchQuery,
    RetrievalQuery,
    Vertical,
)

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
REPO_ROOT = Path(__file__).resolve().parents[2]
_BODY = {"topic": "savings and account fees", "market": "SG", "vertical": "banking"}

_RESEARCH_JSON = json.dumps(
    {
        "sources": [
            {
                "id": "web-1",
                "title": "Fictional bank cuts account fees",
                "url": "https://example.test/fees",
                "publisher": "Example Wire",
                "snippet": "A fictional bank removed its monthly account fee.",
            }
        ],
        "claims": [
            {
                "text": "A fictional bank removed its monthly account fee.",
                "subject": "fees",
                "confidence": 0.8,
                "source_ids": ["web-1"],
            }
        ],
    }
)


# --------------------------------------------------------------------------------------- #
# A fake google.genai: records every call, answers with canned text.
# --------------------------------------------------------------------------------------- #
class _FakeModels:
    def __init__(self, text: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self._text = text

    def generate_content(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text, usage_metadata=None, candidates=[])


def _fake_genai(monkeypatch: pytest.MonkeyPatch, text: str) -> _FakeModels:
    models = _FakeModels(text)
    genai = types.ModuleType("google.genai")
    t = types.ModuleType("google.genai.types")
    ns = lambda **kw: SimpleNamespace(**kw)  # noqa: E731 - a stand-in constructor
    t.GenerateContentConfig = ns  # type: ignore[attr-defined]
    t.Content = ns  # type: ignore[attr-defined]
    t.Part = SimpleNamespace(from_text=ns)  # type: ignore[attr-defined]
    t.Tool = ns  # type: ignore[attr-defined]
    t.GoogleSearch = ns  # type: ignore[attr-defined]
    t.FileSearch = ns  # type: ignore[attr-defined]
    t.ThinkingConfig = ns  # type: ignore[attr-defined]
    t.ThinkingLevel = SimpleNamespace(LOW="LOW", HIGH="HIGH")  # type: ignore[attr-defined]
    genai.types = t  # type: ignore[attr-defined]
    genai.Client = lambda **_: SimpleNamespace(models=models)  # type: ignore[attr-defined]
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setattr(google, "genai", genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", t)
    return models


def _gcp_settings() -> Settings:
    return dataclasses.replace(_settings("local"), profile="gcp")


def _client(monkeypatch: pytest.MonkeyPatch, container: Container) -> TestClient:
    # CI runs the suite with NO profile exported; name the one this test means.
    monkeypatch.setenv("MKT_INTEL_PROFILE", "local")
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def _brief(client: TestClient) -> dict[str, str]:
    response = client.post("/v1/brief", json=_BODY)
    assert response.status_code == 200, response.text
    return dict(response.headers)


# --------------------------------------------------------------------------------------- #
# Through the API.
# --------------------------------------------------------------------------------------- #
def test_the_local_narrator_answers_as_the_stub_the_pill_first_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under ``local`` the pill before and after the answer name the same stub, and no search."""
    container = Container(_settings("local"))
    headers = _brief(_client(monkeypatch, container))
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert container.settings.generator_model == STUB_MODEL
    assert SEARCH_USED not in headers


def test_a_grounded_research_call_says_it_searched(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real Gemini research adapter, with the Google Search tool faked, behind the real API.

    The brief's research goes through ``GeminiDeepResearchAdapter`` (which attaches the
    ``google_search`` tool), the narration through the local stub, so the response names both
    models in call order and says it searched. The next request, on the local research
    adapter, starts fresh: no search is claimed for a call that did not search.
    """
    models = _fake_genai(monkeypatch, _RESEARCH_JSON)
    container = Container(_settings("local"))
    grounded = GeminiDeepResearchAdapter(_gcp_settings())
    local_research = container.research
    container.__dict__["research"] = grounded
    client = _client(monkeypatch, container)

    headers = _brief(client)
    assert headers[ANSWERED_BY] == f"{grounded._model}, {STUB_MODEL}"  # noqa: SLF001
    assert headers[SEARCH_USED] == "true"
    assert models.calls, "the grounded adapter was never called"
    for call in models.calls:
        assert [tool.google_search for tool in call["config"].tools], "no search tool attached"

    container.__dict__["research"] = local_research
    headers = _brief(client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers


def test_the_console_can_read_both_headers_cross_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standalone, the console is another origin, and a browser hides unexposed headers.

    This console calls the service directly rather than through a same-origin proxy, so the
    pills depend on the response exposing both headers (the kit's middleware sends it).
    """
    monkeypatch.setenv("MKT_INTEL_PROFILE", "local")
    client = _client(monkeypatch, Container(_settings("local")))
    response = client.post(
        "/v1/brief",
        json=_BODY,
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200, response.text
    exposed = {
        name.strip().lower()
        for name in response.headers.get("access-control-expose-headers", "").split(",")
    }
    assert {ANSWERED_BY, SEARCH_USED} <= exposed


# --------------------------------------------------------------------------------------- #
# The Gemini adapters, through the fake SDK.
# --------------------------------------------------------------------------------------- #
def _narration() -> LlmRequest:
    return LlmRequest(
        messages=(LlmMessage(role="user", content="Summarise."),),
        response_schema={"type": "object"},
    )


def test_the_gemini_narrator_notes_its_model_and_drafts_with_no_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _fake_genai(monkeypatch, '{"summary": "s", "used_source_ids": []}')
    settings = _gcp_settings()
    with provenance.scope() as record:
        GeminiLLMAdapter(settings).generate(_narration())
    assert record.models == [settings.models.reasoning]
    assert record.search_used is False
    (call,) = models.calls
    assert call["model"] == settings.models.reasoning
    assert "temperature" not in vars(call["config"]), "free sampling must send no temperature"
    assert "tools" not in vars(call["config"])


def test_a_pinned_request_reaches_the_gemini_config(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _fake_genai(monkeypatch, "{}")
    GeminiLLMAdapter(_gcp_settings()).generate(dataclasses.replace(_narration(), temperature=0.0))
    assert models.calls[0]["config"].temperature == 0.0


def test_classification_is_pinned_and_notes_the_triage_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _fake_genai(monkeypatch, "fees")
    settings = _gcp_settings()
    with provenance.scope() as record:
        assert GeminiLLMAdapter(settings).classify("text", ["fees", "rates"]) == "fees"
    assert record.models == [settings.models.triage]
    assert models.calls[0]["config"].temperature == 0.0


def test_both_grounded_research_calls_are_pinned_and_note_model_and_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _fake_genai(monkeypatch, _RESEARCH_JSON)
    settings = _gcp_settings()
    adapter = GeminiDeepResearchAdapter(settings)
    query = ResearchQuery(topic="fees", market=Market.SG, vertical=Vertical.BANKING)
    with provenance.scope() as record:
        adapter.research(query)
    assert record.models == [settings.deep_research.model]
    assert record.search_used is True
    with provenance.scope() as record:
        adapter.competitor_snapshots(Market.SG, Vertical.BANKING, ())
    assert record.models == [settings.deep_research.model]
    assert record.search_used is True
    assert [call["config"].temperature for call in models.calls] == [0.0, 0.0]


def test_a_failed_grounded_call_claims_neither_a_model_nor_a_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _fake_genai(monkeypatch, _RESEARCH_JSON)

    def refuse(**_: Any) -> None:
        raise RuntimeError("the fake backend refused")

    monkeypatch.setattr(models, "generate_content", refuse)
    query = ResearchQuery(topic="fees", market=Market.SG, vertical=Vertical.BANKING)
    with provenance.scope() as record, pytest.raises(RuntimeError):
        GeminiDeepResearchAdapter(_gcp_settings()).research(query)
    assert record.models == []
    assert record.search_used is False


def test_file_search_notes_its_model_but_never_a_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """File Search reads the internal corpus, not the web: it is not an online search."""
    models = _fake_genai(monkeypatch, "")
    settings = _gcp_settings()
    adapter = FileSearchKnowledgeBaseAdapter(settings)
    with provenance.scope() as record:
        adapter.search(RetrievalQuery(text="fees"))
    assert record.models == [adapter._model]  # noqa: SLF001
    assert record.search_used is False
    assert models.calls[0]["config"].temperature == 0.0


# --------------------------------------------------------------------------------------- #
# Sampling is per call, and generator_model is the model the adapter calls.
# --------------------------------------------------------------------------------------- #
def test_the_request_type_samples_freely_unless_a_call_site_pins_it() -> None:
    assert LlmRequest.__dataclass_fields__["temperature"].default is None


def test_the_brief_narration_sends_no_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[LlmRequest] = []
    container = Container(_settings("local"))
    real = container.llm

    class Spy:
        def generate(self, request: LlmRequest) -> Any:
            sent.append(request)
            return real.generate(request)

        def classify(self, text: str, labels: list[str]) -> str:
            return str(real.classify(text, labels))

    container.__dict__["llm"] = Spy()
    _brief(_client(monkeypatch, container))
    assert sent, "the brief made no model call"
    assert all(request.temperature is None for request in sent)


def test_generator_model_is_the_setting_the_gemini_narrator_reads() -> None:
    assert _gcp_settings().generator_model == _gcp_settings().models.reasoning


def test_no_flag_swaps_in_a_model_the_adapter_never_calls() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
