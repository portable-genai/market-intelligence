"""A2A AgentCard for the D1 Market Intelligence agent (A3 Registry & Governance).

This builds the agent's discovery card (the same minimal A2A shape the
``agent-registry`` service stores and serves, SPEC §6). It is published at
``/.well-known/agent-card.json``; :func:`agent_card_document` returns the JSON-safe body
the API layer serves there, and the ``platform`` registry adapter registers the same card
in agent-registry (rule R4).

The card advertises the two consequential skills D1 produces (build_market_brief,
competitor_analysis), mirroring the ADK FunctionTools so a peer agent or the registry sees
one consistent capability surface.

This module is pure (domain models only) and imports without ADK or any Google Cloud SDK
installed (SPEC §4).
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.models import AgentCard, AgentSkill

SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="build_market_brief",
        name="Market brief",
        description=(
            "Build a cited market brief for a topic in a market (JP / AU / SG) and vertical "
            "(banking / online retail): market and segment read, key claims, trend scores, a "
            "competitor read and a narrated summary, grounded in deep research plus the "
            "internal corpus. Always flagged for human review (P-06)."
        ),
    ),
    AgentSkill(
        id="competitor_analysis",
        name="Competitor analysis",
        description=(
            "Run a deterministic competitor-move diff and SWOT / where-to-play synthesis for "
            "a market and vertical, with ranked options and citations. Consequential "
            "strategy input, so it always requires human review (maker-checker)."
        ),
    ),
)

_DESCRIPTION = (
    "Grounded market-intelligence agent for a bank or online retailer. Turns a topic into a "
    "cited market brief and competitor analysis (segment read, competitor moves, trend "
    "scores, SWOT / where-to-play) from grounded deep research plus an internal research "
    "corpus, with a full audit trail. Generic across banking and online retail and the "
    "JP / AU / SG markets. Built ports-and-adapters on the Gemini Enterprise Agent Platform; "
    "the governed RAG store is the enterprise-knowledge-base. The model only narrates the "
    "deterministically-computed result; every claim carries a citation."
)


def build_agent_card(settings: Settings) -> AgentCard:
    """Construct the A2A :class:`AgentCard` for this agent."""
    return AgentCard(
        name="market-intelligence",
        description=_DESCRIPTION,
        url=_resolve_url(settings),
        version="0.1.0",
        skills=SKILLS,
        provider="market-intelligence",
    )


def agent_card_document(settings: Settings) -> dict[str, Any]:
    """Return the JSON-safe body to serve at ``/.well-known/agent-card.json``."""
    from ..domain.serialization import to_jsonable

    return to_jsonable(build_agent_card(settings))


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-pinned to the active market."""
    resource = settings.agent_engine.resource_name
    if resource:
        return f"https://aiplatform.googleapis.com/v1/{resource}"
    return "https://market-intelligence.mkt.internal/a2a"
