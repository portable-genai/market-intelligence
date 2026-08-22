"""Dedicated market-research sub-agent that isolates the built-in ``google_search`` tool.

The Gemini Enterprise Agent Platform allows **only one built-in tool per agent** (SPEC §3
gotcha). The root agent already carries D1's ``FunctionTool`` wrappers, so public-web
market-research grounding via the Gemini API ``google_search`` tool must live in its own
sub-agent. The root agent reaches it as an ``AgentTool`` (an agent-as-tool), keeping the
built-in tool quarantined in this one place.

Public-web grounding is **secondary corroboration** for a brief and is toggled per
deployment via ``settings.grounding_enabled`` (SPEC §2). When disabled this module builds no
sub-agent at all, so no ``google_search`` traffic can leave the tenancy.

``google.adk`` is imported lazily inside the factory so this module imports without ADK
installed (SPEC §4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from google.adk.agents import LlmAgent

GROUNDING_AGENT_NAME = "market_research_grounding"

_INSTRUCTION = (
    "You retrieve secondary, public-web market and competitor evidence for a bank or online "
    "retailer. Use the google_search tool to find credible, recent, citable facts about "
    "market conditions, competitor product / pricing / campaign moves and sector trends in "
    "the requested market (JP / AU / SG). Return concise, quote-backed findings with their "
    "source titles and URLs. Never fabricate a citation, and treat web results as "
    "corroborating evidence only, never as a substitute for the internal research corpus or "
    "the deterministic analysis."
)


def build_grounding_agent(settings: Settings) -> LlmAgent | None:
    """Build the ``google_search``-only market-research sub-agent, or ``None`` if disabled.

    Gated on ``settings.grounding_enabled``. Uses the triage model
    (``settings.models.triage``) because the scan is a cheap, narrow lookup, and carries
    exactly one built-in tool (``google_search``). Imports ``google.adk`` lazily (SPEC §4).
    """
    if not settings.grounding_enabled:
        return None

    from google.adk.agents import LlmAgent
    from google.adk.tools import google_search

    return LlmAgent(
        name=GROUNDING_AGENT_NAME,
        model=settings.models.triage,
        description=(
            "Public-web market-research grounding via the Gemini API google_search tool; "
            "returns secondary, citable market / competitor evidence for a topic and market."
        ),
        instruction=_INSTRUCTION,
        tools=[google_search],
    )
