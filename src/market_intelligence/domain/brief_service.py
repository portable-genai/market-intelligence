"""MarketBriefService — the market-intelligence orchestrator.

Owns the full brief pipeline and calls only ports plus the deterministic engines. The
deterministic engines (dedup, diff, trend, SWOT) decide everything consequential; the LLM
only narrates the already-computed result. Every consequential output is maker-checker
gated: the brief and the competitor analysis always require human review.

Pipeline (each step wrapped in ``tracer.span``; audited at the end):

    tracer.span("brief.build"):
      guardrail.screen(INPUT)                  [blocked -> audit BLOCKED + raise]
      -> research.research(topic, market, vertical)     (deep research / web)
      -> knowledge_base.search(internal corpus)          (brand / internal research)
      -> dedup sources + claims (provenance merge)       [empty -> ResearchEmptyError]
      -> diff competitor moves (prev vs current snapshot)
      -> score trends
      -> synthesize SWOT + where-to-play
      -> llm.generate(summary narrative)   (narration only, over computed result)
      -> assemble MarketBrief (requires_human_review=True)
      -> guardrail.screen(OUTPUT)              [blocked -> audit BLOCKED + raise]
      -> audit.record

Defensive throughout: a research / corpus call that degrades is tolerated, but a blocked
input and a brief with no evidence are hard errors so a brief is never built on
screened-out or absent evidence.

Pure domain code: no Google Cloud / ADK / FastAPI imports.
"""

from __future__ import annotations

import contextlib
import json
from contextlib import nullcontext
from datetime import date
from typing import Any

from .dedup_service import ClaimDedupService
from .diff_service import CompetitorDiffService
from .errors import GuardrailBlockedError, ResearchEmptyError
from .models import (
    AuditEvent,
    BriefRequest,
    Claim,
    CompetitorAnalysis,
    Decision,
    Direction,
    GuardrailVerdict,
    LlmMessage,
    LlmRequest,
    MarketBrief,
    ResearchQuery,
    TrendSignal,
)
from .swot_service import SwotSynthesisService
from .trend_service import TrendScoringService

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
}


class MarketBriefService:
    """Build a cited market brief for a topic. Constructor takes explicit ports."""

    def __init__(
        self,
        research: Any,
        knowledge_base: Any,
        llm: Any,
        guardrail: Any,
        tracer: Any,
        audit: Any,
        dedup: ClaimDedupService | None = None,
        diff: CompetitorDiffService | None = None,
        trend: TrendScoringService | None = None,
        swot: SwotSynthesisService | None = None,
        review_router: Any = None,
    ) -> None:
        self._research = research
        self._knowledge_base = knowledge_base
        self._llm = llm
        self._guardrail = guardrail
        self._tracer = tracer
        self._audit = audit
        self._dedup = dedup or ClaimDedupService()
        self._diff = diff or CompetitorDiffService()
        self._trend = trend or TrendScoringService()
        self._swot = swot or SwotSynthesisService()
        # Rule R8: when the brief requires human review it is routed to Hrz7 (the maker-checker
        # console) via this port instead of terminating in a boolean. Optional: a container that
        # leaves the router unset still audits ESCALATED, it just is not forwarded to a console.
        self._review_router = review_router

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def build_brief(
        self,
        request: BriefRequest,
        actor: str,
        as_of: date | None = None,
        tenant: str = "",
    ) -> MarketBrief:
        as_of = as_of or date.today()
        with self._span("brief.build", market=request.market.value):
            self._guard(request.topic, Direction.INPUT, actor)

            result = self._research.research(
                ResearchQuery(
                    topic=request.topic,
                    market=request.market,
                    vertical=request.vertical,
                    max_sources=request.max_sources,
                    competitors=request.competitors,
                )
            )
            passages = self._search_internal(request)

            sources = self._dedup.dedup_sources(result.sources)
            claims = self._dedup.dedup_claims(
                tuple(result.claims) + self._claims_from_passages(passages, request)
            )
            if not sources and not claims:
                raise ResearchEmptyError(
                    "no sources or claims after dedup; a brief must be grounded"
                )

            analysis = self._competitor_analysis(request, claims, as_of)
            trends = self._trend.score_all(
                self._signals_from_claims(claims), request.market, request.vertical, as_of
            )
            summary = self._narrate(request, claims, actor)

            citations = self._dedup.merge_citations(
                tuple(c for claim in claims for c in claim.citations)
                + tuple(s.to_citation() for s in sources)
            )
            brief = MarketBrief(
                id=f"brief-{request.market.value}-{request.vertical.value}-{as_of.isoformat()}",
                topic=request.topic,
                market=request.market,
                vertical=request.vertical,
                summary=summary,
                key_claims=claims,
                trends=trends,
                competitor_analysis=analysis,
                sources=sources,
                citations=citations,
                requires_human_review=True,
            )
            self._guard(summary, Direction.OUTPUT, actor)
            self._record(brief, actor)
            # Rule R8: the escalation is not left as a boolean — the already-assembled, already-
            # audited brief is handed to the Hrz7 maker-checker console (the audit ESCALATED
            # record is the durable trail). Routing is a hand-off, never fatal to a brief that
            # is already built and audited.
            if self._review_router is not None and brief.requires_human_review:
                with contextlib.suppress(Exception):
                    self._review_router.route(brief, maker=actor, tenant=tenant)
            return brief

    def competitor_analysis(
        self, request: BriefRequest, actor: str, as_of: date | None = None
    ) -> CompetitorAnalysis:
        as_of = as_of or date.today()
        with self._span("competitor.analysis", market=request.market.value):
            self._guard(request.topic, Direction.INPUT, actor)
            result = self._research.research(
                ResearchQuery(
                    topic=request.topic,
                    market=request.market,
                    vertical=request.vertical,
                    max_sources=request.max_sources,
                    competitors=request.competitors,
                )
            )
            claims = self._dedup.dedup_claims(result.claims)
            analysis = self._competitor_analysis(request, claims, as_of)
            self._audit.record(
                AuditEvent(
                    action="competitor_analysis",
                    actor=actor,
                    decision=Decision.ESCALATED
                    if analysis.requires_human_review
                    else Decision.ALLOWED,
                    response=analysis.narrative,
                    citations=analysis.citations,
                    metadata={"market": request.market.value, "vertical": request.vertical.value},
                )
            )
            return analysis

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _competitor_analysis(
        self, request: BriefRequest, claims: tuple[Claim, ...], as_of: date
    ) -> CompetitorAnalysis:
        previous, current = self._research.competitor_snapshots(
            request.market, request.vertical, request.competitors
        )
        diff = self._diff.diff(previous, current, request.market, request.vertical)
        trends = self._trend.score_all(
            self._signals_from_claims(claims), request.market, request.vertical, as_of
        )
        swot = self._swot.synthesize(request.market, request.vertical, diff, trends, claims)
        citations = self._dedup.merge_citations(
            tuple(c for d in diff.deltas for c in d.citations)
            + tuple(c for item in swot.items for c in item.citations)
        )
        narrative = self._narrate_competitor(request, diff, swot)
        return CompetitorAnalysis(
            market=request.market,
            vertical=request.vertical,
            competitors=request.competitors,
            diff=diff,
            swot=swot,
            narrative=narrative,
            citations=citations,
            requires_human_review=True,
        )

    def _search_internal(self, request: BriefRequest) -> list[Any]:
        from .models import RetrievalQuery

        try:
            return list(
                self._knowledge_base.search(
                    RetrievalQuery(
                        text=request.topic,
                        market=request.market,
                        vertical=request.vertical,
                        top_k=request.max_sources,
                    )
                )
            )
        except Exception:  # noqa: BLE001 - internal corpus is best-effort grounding
            return []

    @staticmethod
    def _claims_from_passages(passages: list[Any], request: BriefRequest) -> tuple[Claim, ...]:
        return tuple(
            Claim(
                text=p.text,
                citations=(p.citation,),
                subject=request.topic,
                market=request.market,
                vertical=request.vertical,
                confidence=p.score,
            )
            for p in passages
        )

    @staticmethod
    def _signals_from_claims(claims: tuple[Claim, ...]) -> tuple[TrendSignal, ...]:
        signals: list[TrendSignal] = []
        for claim in claims:
            for c in claim.citations:
                if c.published_date:
                    signals.append(
                        TrendSignal(
                            topic=claim.subject or "topic",
                            observed_date=c.published_date,
                            weight=max(claim.confidence, 0.1),
                            citation=c,
                        )
                    )
        return tuple(signals)

    # ------------------------------------------------------------------ #
    # LLM narration (narration only; never decides the numbers)
    # ------------------------------------------------------------------ #
    def _narrate(self, request: BriefRequest, claims: tuple[Claim, ...], actor: str) -> str:
        evidence = self._render_evidence(claims)
        prompt = (
            f"Write a concise market-brief summary for topic '{request.topic}' in market "
            f"{request.market.value}, vertical {request.vertical.value}. Use ONLY the "
            f"evidence below; cite source ids you used.\n\nEVIDENCE:\n{evidence}"
        )
        response = self._llm.generate(
            LlmRequest(
                messages=(LlmMessage(role="user", content=prompt),),
                response_schema=_SUMMARY_SCHEMA,
            )
        )
        return self._extract_summary(response.text, request)

    def _narrate_competitor(self, request: BriefRequest, diff: Any, swot: Any) -> str:
        moves = "; ".join(
            f"{d.competitor} {d.status.value} {d.summary}" for d in diff.material_deltas
        )
        return (
            f"Competitor analysis for {request.market.value}/{request.vertical.value}: "
            f"{len(diff.material_deltas)} material move(s) [{moves}]; "
            f"{len(swot.options)} where-to-play option(s) identified. "
            "Human review required before acting."
        )

    @staticmethod
    def _render_evidence(claims: tuple[Claim, ...]) -> str:
        lines = []
        for claim in claims:
            ids = " ".join(f"[{c.source_id} p.{c.page or 1}]" for c in claim.citations)
            lines.append(f"{ids} {claim.text}")
        return "\n".join(lines) or "(no evidence)"

    @staticmethod
    def _extract_summary(text: str, request: BriefRequest) -> str:
        try:
            obj = json.loads(text)
            summary = obj.get("summary", "")
            if isinstance(summary, str) and summary:
                return summary
        except (json.JSONDecodeError, AttributeError):
            pass
        return (
            f"Market brief for {request.topic} in {request.market.value} "
            f"({request.vertical.value})."
        )

    # ------------------------------------------------------------------ #
    # Cross-cutting: guardrail, tracing, audit
    # ------------------------------------------------------------------ #
    def _guard(self, text: str, direction: Direction, actor: str) -> None:
        verdict: GuardrailVerdict = self._guardrail.screen(text, direction)
        if not verdict.allowed:
            self._audit.record(
                AuditEvent(
                    action="market_brief",
                    actor=actor,
                    decision=Decision.BLOCKED,
                    prompt=text if direction is Direction.INPUT else "",
                    response=text if direction is Direction.OUTPUT else "",
                    metadata={"reason": verdict.reason, "direction": direction.value},
                )
            )
            raise GuardrailBlockedError(verdict.reason or "guardrail blocked the request")

    def _span(self, name: str, **attrs: str) -> Any:
        try:
            return self._tracer.span(name, **attrs)
        except Exception:  # noqa: BLE001 - tracing must never break the pipeline
            return nullcontext()

    def _record(self, brief: MarketBrief, actor: str) -> None:
        self._audit.record(
            AuditEvent(
                action="market_brief",
                actor=actor,
                decision=Decision.ESCALATED if brief.requires_human_review else Decision.ALLOWED,
                response=brief.summary,
                citations=brief.citations,
                metadata={
                    "market": brief.market.value,
                    "vertical": brief.vertical.value,
                    "topic": brief.topic,
                },
            )
        )
