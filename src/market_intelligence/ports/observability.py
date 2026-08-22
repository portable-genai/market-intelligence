"""Observability ports — the A5 (audit/trace) and A4 (eval gate) concerns.

Two of the three boundaries here are NOT declared in this file. ``ObservabilityTracerPort`` and
``TokenUsage`` come from ``hex-service-kit`` and ``EvaluationGatePort`` from ``agent-eval-kit``,
for the same reason ``IdentityPort`` does: sixteen repositories each hand-copied these Protocols
and they had already drifted apart. One had dropped the evaluation port entirely, two had dropped
its ``gate`` method and kept only ``evaluate``, which is the half that cannot refuse a promotion.
A Protocol copied into N repositories is N Protocols, and only one of them gets fixed when a
defect is found.

``AuditSinkPort`` stays declared here, deliberately: it is typed in THIS repo's vocabulary
(:class:`~market_intelligence.domain.models.AuditEvent`), so it is not a shared shape.

Both imports are typing-only, so this module costs the offline profile nothing: no
OpenTelemetry, no HTTP client, no cloud SDK. The OpenTelemetry implementation lives in
``hex_service_kit.tracing`` behind the ``otel`` extra and is reached only by the GCP adapter.

Primary GCP adapters: a **Cloud Logging locked WORM bucket** for immutable audit, **Cloud
Trace via OpenTelemetry** for the reasoning-loop traces, and the **Gen AI evaluation
service** plus the A4 promotion gate for model risk.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_eval_kit import EvaluationGatePort
from hex_service_kit.observability import ObservabilityTracerPort, TokenUsage

from ..domain.models import AuditEvent


@runtime_checkable
class AuditSinkPort(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Write an immutable audit record (WORM)."""
        ...


__all__ = [
    "AuditSinkPort",
    "EvaluationGatePort",
    "ObservabilityTracerPort",
    "TokenUsage",
]
