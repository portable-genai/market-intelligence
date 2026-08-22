"""ADK FunctionTools that expose the D1 domain services to the agent.

Each tool is a thin, side-effect-honest wrapper: it builds the :class:`MarketBriefService`
from a :class:`~market_intelligence.config.Container` (so every port is bound to the adapter
selected by the active profile), invokes one domain method, and returns a JSON-safe dict via
:func:`~market_intelligence.domain.serialization.to_jsonable`.

Design notes
------------
* The domain service owns orchestration (guardrail -> deep research -> internal corpus ->
  dedup -> diff -> trend -> SWOT -> narrate -> guardrail -> audit; SPEC §5). These tools add
  **no** business logic of their own: the model decides *which* artifact to produce, the
  service decides *how* and owns every consequential number (the LLM only narrates).
* ``google.adk`` is imported lazily inside :func:`build_function_tools` so this module
  imports cleanly under the on-prem / local / test profile with no ADK installed (SPEC §4).
  The plain Python tool callables are importable and unit-testable without ADK at all.
* Every callable carries a precise type-hinted signature and docstring: ADK derives the
  tool's name, description and JSON parameter schema from them.
* Least privilege (rule R4): the callables mirror the governed MCP tool catalog
  (``adapters/gcp/mcp_tool_catalog.py``); :func:`governed_tool_names` lets the wiring assert
  the surfaces stay in step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Container, Settings, build_container

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

_DEFAULT_ACTOR = "market-intelligence-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _brief_service(container: Container) -> Any:
    from ..api.deps import make_brief_service

    return make_brief_service(container)


def _request(
    topic: str,
    market: str,
    vertical: str,
    competitors: tuple[str, ...] = (),
    max_sources: int = 12,
) -> Any:
    from ..domain.models import BriefRequest, Market, Vertical

    return BriefRequest(
        topic=topic,
        market=Market(market),
        vertical=Vertical(vertical),
        competitors=tuple(competitors),
        max_sources=max_sources,
    )


def build_market_brief(
    topic: str,
    market: str = "SG",
    vertical: str = "banking",
    competitors: list[str] | None = None,
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build a cited market brief for a topic in a market and vertical.

    Runs the full grounded pipeline (deep research + internal corpus, deterministic
    dedup / diff / trend / SWOT, narration over the computed result) and returns a
    ``MarketBrief``. Always flagged for human review (maker-checker); every claim carries a
    citation.

    Args:
      topic: The topic to brief on, e.g. "savings rates".
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      competitors: Optional list of competitor names to restrict the analysis to.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``MarketBrief`` dict.
    """
    from ..domain.serialization import to_jsonable

    c = _container(settings)
    request = _request(topic, market, vertical, tuple(competitors or ()))
    return to_jsonable(_brief_service(c).build_brief(request, actor=actor))


def competitor_analysis(
    topic: str,
    market: str = "SG",
    vertical: str = "banking",
    competitors: list[str] | None = None,
    actor: str = _DEFAULT_ACTOR,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run a deterministic competitor-move diff and SWOT / where-to-play synthesis.

    Returns a ``CompetitorAnalysis`` (the move diff plus the SWOT and ranked where-to-play
    options) for the market and vertical. Consequential strategy input, so it always
    requires human review (maker-checker).

    Args:
      topic: The area to analyse, e.g. "digital onboarding".
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      competitors: Optional list of competitor names to restrict the analysis to.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``CompetitorAnalysis`` dict.
    """
    from ..domain.serialization import to_jsonable

    c = _container(settings)
    request = _request(topic, market, vertical, tuple(competitors or ()))
    return to_jsonable(_brief_service(c).competitor_analysis(request, actor=actor))


TOOL_FUNCTIONS = (
    build_market_brief,
    competitor_analysis,
)


def governed_tool_names() -> frozenset[str]:
    """The tool names this agent exposes (mirrors the governed MCP catalog, rule R4)."""
    return frozenset(fn.__name__ for fn in TOOL_FUNCTIONS)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each domain-service callable as an ADK ``FunctionTool``.

    ADK introspects each function's signature and docstring to derive the tool name,
    description and parameter JSON schema. ``google.adk`` is imported here (lazily) so the
    module is import-safe without ADK installed (SPEC §4).
    """
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=fn) for fn in TOOL_FUNCTIONS]
