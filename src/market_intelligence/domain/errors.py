"""Domain exceptions for the Market Intelligence system (D1).

Pure-Python exception hierarchy raised by the orchestration services. The domain layer
never imports Google Cloud, ADK, or any framework: these errors let callers (API, CLI,
the agent runtime adapter) react to domain-level failures without coupling to any vendor
SDK error type.
"""

from __future__ import annotations


class MarketIntelError(Exception):
    """Base class for all domain-level errors raised by D1 services."""


class GuardrailBlockedError(MarketIntelError):
    """Flagged/raised when the A1 guardrail blocks an input or output.

    A blocked unsafe request must never yield a partial brief: the orchestrator raises
    this rather than assembling a brief from screened-out content.
    """


class ResearchEmptyError(MarketIntelError):
    """Raised when deep research and the internal corpus return no sources.

    A market brief must be grounded; an empty research result is a hard error so a brief
    is never built on no evidence.
    """


class GroundingDisabledError(MarketIntelError):
    """Raised when public-web grounding is requested but switched off in config."""


class UnsupportedMarketError(MarketIntelError):
    """Raised when a requested market has no configured residency region / profile."""


class UnsupportedVerticalError(MarketIntelError):
    """Raised when a requested vertical has no configured seed / taxonomy."""
