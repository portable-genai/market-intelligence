"""Remote-platform evaluation adapter : thin HTTP client to Hrz4.

At promotion this vertical's quality is checked against the shared **Hrz4 AI Quality /
model-risk** service (``model-quality-gate``). This adapter implements
:class:`EvaluationGatePort` against Hrz4's hardened contract:

* ``evaluate`` -> ``POST /v1/evaluations {target, dataset_id, bundle}`` -> EvalReport.
* ``gate``     -> ``POST /v1/gate {target, dataset_id, bundle}`` -> ``{passed}``.

**Sourced from the shared ``agent-eval-kit`` commons.** The HTTP contract
is ``agent_eval_kit.gate_client.PromotionGateClient``; this adapter configures it (the
registered ``mkt1-market-intel`` bundle, the reasoning model, and this repo's S2S auth
headers) and re-raises its errors as :class:`RemoteEvaluationError`. The client's
:class:`EvalReport` IS the domain's, so the report is returned unchanged and its durable
identifiers, artifact refs and attestation flag survive.
"""

from __future__ import annotations

from agent_eval_kit.gate_client import GateClientError, PromotionGateClient

from ...config import Settings
from ...domain.errors import MarketIntelError
from ...domain.models import EvalReport
from ...envread import setting_or_default
from . import _s2s

_DEFAULT_URL = "http://localhost:8084"

#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + bars).
_BUNDLE = "mkt1-market-intel"
#: Prompt/agent version tag; bump when the prompt corpus changes, or source it from a registry.
_PROMPT_VERSION = "v1"


class RemoteEvaluationError(MarketIntelError):
    """Raised when the Hrz4 quality service returns a non-2xx response."""


class RemoteEvaluationAdapter:
    """HTTP client for the Hrz4 ``model-quality-gate`` service (via PromotionGateClient)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = PromotionGateClient(
            setting_or_default("QUALITY_GATE_URL", _DEFAULT_URL),
            bundle=_BUNDLE,
            model=settings.models.reasoning,
            prompt_version=_PROMPT_VERSION,
            auth_headers=lambda: _s2s.headers(),
        )

    def evaluate(self, dataset_path: str) -> EvalReport:
        """Score ``dataset_path`` via Hrz4 and return a domain EvalReport."""
        try:
            report = self._client.evaluate(dataset_path)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc
        # Returned UNCHANGED. There is deliberately no ``_to_domain`` mapper here rebuilding an
        # EvalReport from three of its fields. Because the domain re-exports the commons
        # EvalReport, such a mapper is an identity function with a leak: it silently drops
        # run_id, dataset_version, dataset_digest, evaluator, schema_version, trace_id,
        # correlation_id, artifact_refs and attested, which is exactly the attested evidence
        # the client had just validated on the wire.
        return report

    def gate(self, target: str) -> bool:
        """Promotion gate: True iff Hrz4 reports ``target`` passes."""
        try:
            return self._client.gate(target)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc
