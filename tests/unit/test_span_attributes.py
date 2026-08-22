"""Span ATTRIBUTES carry structure, never content, and this is the test that can tell.

The pipeline tests wire the real ``LocalNoopTracerAdapter``, whose ``span`` is a
``nullcontext``: it observes nothing, so a span that started carrying the researched topic,
a source snippet or the drafted summary would keep every existing test green. A trace
backend is not the WORM audit trail. It has no redaction stage, a wider read audience and no
retention rule written against a regulator's requirement, so an attribute is OUTSIDE the
boundary the audit sink and the guardrail hold.

The recording tracer here keeps ``dict(attributes)`` and drives the two real request paths,
``build_brief`` and ``competitor_analysis``, over the local seeded corpus. The content case
uses a topic carrying a planted NRIC and a rival's address, so a leak fails on the planted
literal rather than on a subtlety.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from datetime import date

import pytest

from market_intelligence.config import Container, Settings
from market_intelligence.domain.models import BriefRequest, Market, TokenUsage, Vertical
from market_intelligence.domain.services import MarketBriefService

AS_OF = date(2026, 6, 24)
ACTOR = "analyst@bank.example"

#: The complete attribute key set an Mkt1 span may carry, per span name. Widening one of
#: these is a decision about what leaves the trust boundary, so it is made here rather
#: than at a call site.
_ALLOWED = {
    "brief.build": {"market"},
    "competitor.analysis": {"market"},
}

#: A topic with planted identifiers. The guardrail does not block it (it is not an
#: injection), so it flows the whole way through research, dedup, narration and audit,
#: which is exactly the path a leak would ride.
_PLANTED_NRIC = "S1234567D"
_PLANTED_EMAIL = "analyst@rival.example"
_PLANTED_TOPIC = f"savings moves for {_PLANTED_NRIC} reported by {_PLANTED_EMAIL}"


class _AttributeRecordingTracer:
    """Keeps (name, attributes) per span; the local adapter records nothing at all."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    def span(self, name: str, **attributes: str) -> AbstractContextManager[None]:
        self.spans.append((name, dict(attributes)))
        return nullcontext()

    def record_token_usage(self, usage: TokenUsage, model: str) -> None:
        return None


@pytest.fixture
def tracer() -> _AttributeRecordingTracer:
    return _AttributeRecordingTracer()


def _service(container: Container, tracer: _AttributeRecordingTracer) -> MarketBriefService:
    return MarketBriefService(
        research=container.research,
        knowledge_base=container.knowledge_base,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=tracer,
        audit=container.audit,
    )


def _drive_every_span_site(
    container: Container, tracer: _AttributeRecordingTracer, topic: str
) -> None:
    service = _service(container, tracer)
    request = BriefRequest(topic=topic, market=Market.SG, vertical=Vertical.BANKING)
    service.build_brief(request, actor=ACTOR, as_of=AS_OF)
    service.competitor_analysis(request, actor=ACTOR, as_of=AS_OF)


def test_the_request_paths_open_exactly_the_known_spans(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    _drive_every_span_site(local_container, tracer, "competitor moves")
    names = {name for name, _ in tracer.spans}
    assert names == set(_ALLOWED), (
        "the set of spans these request paths open changed; a new span site is a "
        "trust-boundary decision, so record it in _ALLOWED here deliberately"
    )


def test_every_span_carries_allowlisted_keys_only(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    _drive_every_span_site(local_container, tracer, "competitor moves")
    assert tracer.spans, "the request paths opened no span at all"
    for name, attributes in tracer.spans:
        assert name in _ALLOWED, f"unexpected span {name!r}; add it here deliberately"
        assert set(attributes) == _ALLOWED[name], (
            f"span {name!r} attribute keys changed; widening the set is a trust-boundary "
            "decision, so update _ALLOWED here deliberately"
        )


def test_no_span_attribute_carries_the_planted_identifiers(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    _drive_every_span_site(local_container, tracer, _PLANTED_TOPIC)
    emitted = " ".join(value for _, attributes in tracer.spans for value in attributes.values())
    assert _PLANTED_NRIC not in emitted, "an NRIC in the topic reached a span attribute"
    assert _PLANTED_EMAIL not in emitted, "an email in the topic reached a span attribute"
    assert _PLANTED_TOPIC not in emitted, "the researched topic reached a span attribute"


def test_no_span_attribute_carries_the_seeded_corpus_content(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    """Source titles and snippets are retrieved content, not span structure."""
    _drive_every_span_site(local_container, tracer, "competitor moves")
    emitted = " ".join(value for _, attributes in tracer.spans for value in attributes.values())
    assert "FICTIONAL" not in emitted, (
        "the seeded corpus marks every synthetic title, snippet and publisher FICTIONAL; "
        "seeing one in a span attribute means retrieved content reached the trace"
    )


def test_every_attribute_value_is_a_string(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    """The port declares str values; a structured object smuggles content past a grep."""
    _drive_every_span_site(local_container, tracer, "competitor moves")
    for name, attributes in tracer.spans:
        for key, value in attributes.items():
            assert isinstance(value, str), f"span {name!r} attribute {key!r} is not a str"


def test_the_recorder_satisfies_the_tracer_port(local_container: Container) -> None:
    """The guard is only evidence if the service accepts the recorder as its tracer."""
    from market_intelligence.ports.observability import ObservabilityTracerPort

    assert isinstance(_AttributeRecordingTracer(), ObservabilityTracerPort)
    assert isinstance(local_container.settings, Settings)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
