"""Ports — the abstract interfaces (the hexagon boundary).

Every port is a ``typing.Protocol`` (``@runtime_checkable``) so adapters need only
structural conformance and the contract test can verify any adapter family (GCP,
remote-platform, on-prem placeholder, or local) satisfies the same contract.

``IdentityPort``, ``ObservabilityTracerPort``, ``EvaluationGatePort`` and the ``TokenUsage``
value type are not redeclared: they come from the shared commons packages and are re-exported
here so consumers still have one import site for the boundary set. Copies of these had already
drifted apart across the fleet before they were shared, which is the whole reason they are
imported rather than typed out. See :mod:`.observability`.
"""

from .generation import LlmPort
from .governance import AgentRegistryPort, ToolCatalogPort
from .identity import EndUserAuthUnavailableError, IdentityPort
from .knowledge_base import KnowledgeBasePort
from .observability import (
    AuditSinkPort,
    EvaluationGatePort,
    ObservabilityTracerPort,
    TokenUsage,
)
from .research import ResearchPort
from .review_router import ReviewRouterPort
from .safety import GuardrailPort

__all__ = [
    "ResearchPort",
    "LlmPort",
    "KnowledgeBasePort",
    "GuardrailPort",
    "AuditSinkPort",
    "ObservabilityTracerPort",
    "EvaluationGatePort",
    "AgentRegistryPort",
    "ToolCatalogPort",
    "IdentityPort",
    "EndUserAuthUnavailableError",
    "ReviewRouterPort",
    "TokenUsage",
]
