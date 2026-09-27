"""The Model Armor adapter allows only a complete, clean screen, and fails closed otherwise.

The adapter calls Model Armor's REST API and parses the JSON body. The verdict is ALLOWED only
when ``sanitizationResult.filterMatchState`` is ``NO_MATCH_FOUND`` AND
``sanitizationResult.invocationResult`` is ``SUCCESS``. The mapping this replaces allowed
whenever the state was anything but ``MATCH_FOUND`` (so ``FILTER_MATCH_STATE_UNSPECIFIED``
passed), allowed when the state was absent and no filter node matched (so a missing or empty
``sanitizationResult`` passed), and never read ``invocationResult`` (so ``PARTIAL`` and
``FAILURE`` passed). A skipped filter reports ``NO_MATCH_FOUND``: padding a prompt past the
prompt-injection filter's token limit would otherwise get it through unscreened.

This module tests at two levels:

* **SDK-free** (always runs, including the offline gate, which installs no GCP SDK): the
  JSON bodies are built from ``_MirrorState`` / ``_MirrorInvocation``, stdlib ``IntEnum``s
  with the real member names and numbers.
* **Real SDK** (runs where ``google-cloud-modelarmor`` is installed, skips otherwise): the
  responses are real ``modelarmor_v1`` messages serialised to the REST wire shape with the
  SDK's own JSON encoder, then screened through ``screen()`` with a fake HTTP client, so
  nothing touches the network. The first of these pins the mirror to the real enums, so the
  SDK-free half cannot drift.
"""

from __future__ import annotations

import enum
import json
from typing import Any

import pytest

from market_intelligence.adapters.gcp.model_armor_guardrail import ModelArmorGuardrailAdapter
from market_intelligence.config import Settings
from market_intelligence.domain.models import Direction

CONFIG_PATH = "config/settings.yaml"
TEXT = "Summarise the competitor landscape for retail banking in SG."
DIRECTIONS = [Direction.INPUT, Direction.OUTPUT]


class _MirrorState(enum.IntEnum):
    """``modelarmor_v1.FilterMatchState``'s members, by name and number."""

    FILTER_MATCH_STATE_UNSPECIFIED = 0
    NO_MATCH_FOUND = 1
    MATCH_FOUND = 2


class _MirrorInvocation(enum.IntEnum):
    """``modelarmor_v1.InvocationResult``'s members, by name and number."""

    INVOCATION_RESULT_UNSPECIFIED = 0
    SUCCESS = 1
    PARTIAL = 2
    FAILURE = 3


class _FakeResponse:
    def __init__(self, body: Any) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._body


class _FakeHttp:
    """Stands in for ``httpx.Client``: returns a canned JSON body, or raises the canned error."""

    def __init__(self, body: Any = None, error: Exception | None = None) -> None:
        self._body = body
        self._error = error
        self.urls: list[str] = []
        self.timeouts: list[Any] = []

    def post(self, url: str, *, json: Any, headers: Any, timeout: Any = None) -> _FakeResponse:
        self.urls.append(url)
        self.timeouts.append(timeout)
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._body)


def _adapter(http: _FakeHttp, monkeypatch: pytest.MonkeyPatch) -> ModelArmorGuardrailAdapter:
    adapter = ModelArmorGuardrailAdapter(Settings.load(CONFIG_PATH))
    adapter._client = http  # skip the real client; the mapping is what is under test
    monkeypatch.setattr(adapter, "_bearer_token", lambda: "test-token")
    return adapter


def _screen(
    body: Any, monkeypatch: pytest.MonkeyPatch, direction: Direction = Direction.INPUT
) -> Any:
    return _adapter(_FakeHttp(body), monkeypatch).screen(TEXT, direction)


def _mirror_body(
    state: _MirrorState | None, invocation: _MirrorInvocation | None = _MirrorInvocation.SUCCESS
) -> dict[str, Any]:
    result: dict[str, Any] = {"filterResults": {}}
    if state is not None:
        result["filterMatchState"] = state.name
    if invocation is not None:
        result["invocationResult"] = invocation.name
    return {"sanitizationResult": result}


# --------------------------------------------------------------------------- #
# SDK-free: the mapping itself, on the REST wire shape
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks_sdk_free(direction: Direction, monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = _screen(_mirror_body(_MirrorState.MATCH_FOUND), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert verdict.findings


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows_sdk_free(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND), monkeypatch, direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT
    assert verdict.findings == ()


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "invocation",
    [
        _MirrorInvocation.PARTIAL,
        _MirrorInvocation.FAILURE,
        _MirrorInvocation.INVOCATION_RESULT_UNSPECIFIED,
        None,
    ],
    ids=["PARTIAL", "FAILURE", "UNSPECIFIED", "absent"],
)
def test_no_match_from_an_incomplete_screen_blocks_sdk_free(
    direction: Direction, invocation: _MirrorInvocation | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skipped filter reports no match. That is not a pass: the text was not screened."""
    verdict = _screen(_mirror_body(_MirrorState.NO_MATCH_FOUND, invocation), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_exactly_one_combination_allows_sdk_free(monkeypatch: pytest.MonkeyPatch) -> None:
    states: list[_MirrorState | None] = [*_MirrorState, None]
    invocations: list[_MirrorInvocation | None] = [*_MirrorInvocation, None]
    allowed = [
        (state and state.name, invocation and invocation.name)
        for state in states
        for invocation in invocations
        if _screen(_mirror_body(state, invocation), monkeypatch).allowed
    ]
    assert allowed == [("NO_MATCH_FOUND", "SUCCESS")]


@pytest.mark.parametrize(
    "body",
    [
        _mirror_body(_MirrorState.FILTER_MATCH_STATE_UNSPECIFIED),
        _mirror_body(None),
        {"sanitizationResult": {}},
        {"sanitizationResult": None},
        {},
        [],
        None,
        # Integer-encoded enums are not the REST wire's shape; they must not read as a pass.
        {"sanitizationResult": {"filterMatchState": 1, "invocationResult": 1}},
    ],
    ids=[
        "unspecified-state",
        "absent-state",
        "empty-result",
        "null-result",
        "no-result",
        "non-object-body",
        "null-body",
        "integer-enums",
    ],
)
def test_no_verdict_fails_closed_sdk_free(body: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = _screen(body, monkeypatch)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_call_carries_the_deadline(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    http = _FakeHttp(_mirror_body(_MirrorState.NO_MATCH_FOUND))
    _adapter(http, monkeypatch).screen(TEXT, direction)
    assert http.timeouts == [Settings().model_armor.timeout_seconds]
    assert http.timeouts[0] > 0


def test_api_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """An API failure must not turn into an allow; it reaches the caller."""
    boom = RuntimeError("Model Armor unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        _adapter(_FakeHttp(error=boom), monkeypatch).screen(TEXT, Direction.INPUT)


# --------------------------------------------------------------------------- #
# Real SDK: real modelarmor_v1 messages, serialised to the REST wire, through screen()
# --------------------------------------------------------------------------- #
def _ma() -> Any:
    return pytest.importorskip("google.cloud.modelarmor_v1")


def _real_body(
    direction: Direction,
    state_name: str | None,
    invocation_name: str = "SUCCESS",
    *,
    skipped: bool = False,
) -> Any:
    """A real sanitize response as the REST API returns it; ``state_name=None`` leaves
    ``sanitization_result`` unset.

    ``skipped`` adds the prompt-injection filter as not having run, the shape a prompt padded
    past that filter's token limit produces.
    """
    ma = _ma()
    cls = (
        ma.SanitizeUserPromptResponse
        if direction is Direction.INPUT
        else ma.SanitizeModelResponseResponse
    )
    if state_name is None:
        message = cls()
    else:
        filter_results = {}
        if skipped:
            filter_results["pi_and_jailbreak"] = ma.FilterResult(
                pi_and_jailbreak_filter_result=ma.PiAndJailbreakFilterResult(
                    execution_state=ma.FilterExecutionState.EXECUTION_SKIPPED,
                    match_state=ma.FilterMatchState.NO_MATCH_FOUND,
                )
            )
        message = cls(
            sanitization_result=ma.SanitizationResult(
                filter_match_state=ma.FilterMatchState[state_name],
                invocation_result=ma.InvocationResult[invocation_name],
                filter_results=filter_results,
            )
        )
    # The REST wire: camelCase fields, enums by name.
    return json.loads(cls.to_json(message, use_integers_for_enums=False))


@pytest.mark.parametrize(
    ("mirror", "real_name"),
    [(_MirrorState, "FilterMatchState"), (_MirrorInvocation, "InvocationResult")],
    ids=["FilterMatchState", "InvocationResult"],
)
def test_the_mirror_matches_the_real_enum(mirror: Any, real_name: str) -> None:
    real = getattr(_ma(), real_name)
    assert {m.name: int(m) for m in real} == {m.name: int(m) for m in mirror}


def test_the_real_wire_shape_is_what_the_parser_reads() -> None:
    body = _real_body(Direction.INPUT, "NO_MATCH_FOUND")
    assert body["sanitizationResult"]["filterMatchState"] == "NO_MATCH_FOUND"
    assert body["sanitizationResult"]["invocationResult"] == "SUCCESS"


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks(direction: Direction, monkeypatch: pytest.MonkeyPatch) -> None:
    http = _FakeHttp(_real_body(direction, "MATCH_FOUND"))
    verdict = _adapter(http, monkeypatch).screen(TEXT, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert len(http.urls) == 1


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows(
    direction: Direction, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_real_body(direction, "NO_MATCH_FOUND"), monkeypatch, direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "state_name",
    [None, "FILTER_MATCH_STATE_UNSPECIFIED"],
    ids=["missing-result", "unspecified-state"],
)
def test_no_verdict_fails_closed(
    direction: Direction, state_name: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = _screen(_real_body(direction, state_name), monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation_name", ["PARTIAL", "FAILURE", "INVOCATION_RESULT_UNSPECIFIED"])
def test_no_match_from_a_screen_where_filters_did_not_run_blocks(
    direction: Direction, invocation_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _real_body(direction, "NO_MATCH_FOUND", invocation_name, skipped=True)
    verdict = _screen(body, monkeypatch, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_api_errors_propagate_real_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real SDK error type (a 503 from the API) reaches the caller, never an allow."""
    _ma()
    from google.api_core import exceptions

    boom = exceptions.ServiceUnavailable("Model Armor unavailable")
    with pytest.raises(exceptions.ServiceUnavailable):
        _adapter(_FakeHttp(error=boom), monkeypatch).screen(TEXT, Direction.OUTPUT)
