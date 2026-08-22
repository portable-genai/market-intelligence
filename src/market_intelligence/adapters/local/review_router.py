"""Local ReviewRouterPort: enqueue the routed review to an in-memory outbox (no live Hrz7).

Exercises the R8 routing path offline: an escalated brief is converted to a review and enqueued
(the same transactional outbox the platform adapter flushes to Hrz7), so tests and the offline
demo can assert that an escalation is routed without a running console.
"""

from __future__ import annotations

from review_kit import InMemoryOutbox

from ...config import Settings
from ...domain.models import MarketBrief
from .._review_payload import brief_to_review


class LocalReviewRouter:
    """Record routed reviews in an in-memory outbox for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._outbox = InMemoryOutbox()

    def route(self, brief: MarketBrief, *, maker: str, tenant: str = "") -> None:
        self._outbox.enqueue(
            brief_to_review(brief, maker=maker, tenant=tenant), actor="market-intelligence"
        )

    @property
    def outbox(self) -> InMemoryOutbox:
        """Expose the outbox for inspection in tests and the demo."""
        return self._outbox
