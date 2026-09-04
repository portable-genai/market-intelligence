"""R8 routing: an escalated market brief is routed to human-review-console via the shared
review-kit.

Every market brief requires human review (P-06), so rule R8 says it MUST be handed to the
human-review-console maker-checker console rather than left as a boolean. These tests prove the
producer half of that loop end-to-end against the offline local router (an in-memory outbox), and
prove the redact- before-wire boundary so no stray identifier reaches the console. All data is
fictional.
"""

from __future__ import annotations

from datetime import date

import pytest

from market_intelligence.adapters._review_payload import brief_to_review
from market_intelligence.adapters.local.review_router import LocalReviewRouter
from market_intelligence.config import Container, Settings
from market_intelligence.domain.models import (
    Citation,
    CompetitorAnalysis,
    CompetitorDiff,
    Market,
    MarketBrief,
    MoveDelta,
    MoveKind,
    MoveStatus,
    Severity,
    SourceType,
    SwotSynthesis,
    Vertical,
)
from market_intelligence.domain.services import MarketBriefService

ACTOR = "strategist@brand.test"
TENANT = "demo-brand"
AS_OF = date(2026, 6, 24)


def _service(container: Container, router: LocalReviewRouter | None) -> MarketBriefService:
    return MarketBriefService(
        research=container.research,
        knowledge_base=container.knowledge_base,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        review_router=router,
    )


def test_build_routes_escalated_brief_to_outbox(local_container: Container):
    """A completed build enqueues one review to the router's outbox, carrying the tenant (R8)."""
    from market_intelligence.domain.models import BriefRequest

    router = LocalReviewRouter(Settings())
    service = _service(local_container, router)
    assert not router.outbox.pending()

    request = BriefRequest(topic="competitor moves", market=Market.SG, vertical=Vertical.BANKING)
    brief = service.build_brief(request, actor=ACTOR, as_of=AS_OF, tenant=TENANT)
    assert brief.requires_human_review

    pending = router.outbox.pending()
    assert len(pending) == 1, (
        "the escalated brief must be routed to human-review-console exactly once"
    )
    review = pending[0].review
    assert review.action == "market_brief:build"
    assert review.case_ref == brief.id
    assert review.maker == ACTOR
    assert review.tenant == TENANT


def _high_signal_brief_with_pii() -> MarketBrief:
    # A citation snippet carrying a synthetic SG NRIC + email: both must be masked before the wire.
    cite = Citation(
        source_id="src-1",
        source_type=SourceType.NEWS,
        title="Trade press item",
        snippet="Contact S1234567D at analyst@rival.example about the launch.",
    )
    delta = MoveDelta(
        id="rival:product_launch:premier-account",
        competitor="Rival Bank (FICTIONAL)",
        kind=MoveKind.PRODUCT_LAUNCH,
        status=MoveStatus.NEW,
        summary="Launched a premier savings account.",
        severity=Severity.HIGH,
        citations=(cite,),
    )
    diff = CompetitorDiff(market=Market.SG, vertical=Vertical.BANKING, deltas=(delta,))
    analysis = CompetitorAnalysis(
        market=Market.SG,
        vertical=Vertical.BANKING,
        competitors=("Rival Bank (FICTIONAL)",),
        diff=diff,
        swot=SwotSynthesis(market=Market.SG, vertical=Vertical.BANKING),
        citations=(cite,),
    )
    return MarketBrief(
        id="brief-SG-banking-2026-06-24",
        topic="premier savings competition",
        market=Market.SG,
        vertical=Vertical.BANKING,
        summary="A rival launched a premier savings account.",
        competitor_analysis=analysis,
        citations=(cite,),
    )


def test_payload_is_redacted_and_dual_controls_high_signal():
    """The wire payload masks identifiers, maps severity, and dual-controls a HIGH move (R1/R8)."""
    review = brief_to_review(_high_signal_brief_with_pii(), maker=ACTOR, tenant=TENANT)

    assert review.tenant == TENANT
    assert review.severity == "high"
    assert review.required_approvals == 2, "a HIGH-severity competitor move warrants dual control"
    # No raw identifier survives into the payload the console receives.
    for citation in review.citations:
        assert "S1234567D" not in citation.snippet
        assert "analyst@rival.example" not in citation.snippet
    assert any(c.title == "Trade press item" for c in review.citations)


def test_no_signal_brief_defaults_to_medium_single_control():
    """A brief with no competitor analysis has no risk band: severity medium, single approval."""
    brief = MarketBrief(
        id="brief-AU-online_retail-2026-06-24",
        topic="free shipping trends",
        market=Market.AU,
        vertical=Vertical.ONLINE_RETAIL,
        summary="No material competitor moves this period.",
    )
    review = brief_to_review(brief, maker=ACTOR, tenant=TENANT)
    assert review.severity == "medium"
    assert review.required_approvals == 1


def test_no_router_still_builds_brief(local_container: Container):
    """Routing is optional: with no router bound, build still returns an escalated brief."""
    from market_intelligence.domain.models import BriefRequest

    service = _service(local_container, None)
    request = BriefRequest(topic="competitor moves", market=Market.SG, vertical=Vertical.BANKING)
    brief = service.build_brief(request, actor=ACTOR, as_of=AS_OF)
    assert brief.requires_human_review


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
