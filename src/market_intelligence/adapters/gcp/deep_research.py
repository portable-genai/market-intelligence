"""Gemini Deep Research adapter (ResearchPort) — GCP managed stack.

The primary D1 research backend: the **Gemini Deep Research API** for market research and
competitor analysis, plus **Grounding with Google Search** for live external evidence. Web
egress is isolated in this single grounding sub-agent so it never mixes with the internal
File Search corpus (per the SPEC, one built-in tool per agent).

The adapter drives the Deep Research flow over the unified **Google GenAI SDK**
(``google-genai``) on the **Gemini Enterprise Agent Platform** (Vertex backend), structures
the model's output into the domain :class:`ResearchResult` (cited :class:`ResearchSource` +
extracted :class:`Claim`) and the previous/current :class:`CompetitorMove` snapshots the
deterministic diff engine compares. It never synthesises the brief itself: the LLM only
researches and extracts, the deterministic engines decide.

The residency region is resolved from the requested market and **validated** against the
per-market allow-list (JP -> ``asia-northeast1``, AU -> ``australia-southeast1``, SG ->
``asia-southeast1``), so a research call can never cross the configured residency boundary.

All Google Cloud / GenAI SDK imports are LAZY (inside methods) so the on-prem / local / test
profile imports this module with no ``google-genai`` installed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import (
    Citation,
    Claim,
    CompetitorMove,
    Market,
    MoveKind,
    ResearchQuery,
    ResearchResult,
    ResearchSource,
    SourceType,
    Vertical,
)
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google import genai

# JSON schema the model fills for structured deep-research output. Keeping extraction
# structured (not free text) is what lets the deterministic engines consume it verbatim.
_RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "publisher": {"type": "string"},
                    "published_date": {"type": "string"},
                    "snippet": {"type": "string"},
                },
                "required": ["id", "title", "url"],
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "subject": {"type": "string"},
                    "confidence": {"type": "number"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "source_ids"],
            },
        },
    },
    "required": ["sources", "claims"],
}

_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "previous": {"$ref": "#/$defs/moves"},
        "current": {"$ref": "#/$defs/moves"},
    },
    "$defs": {
        "moves": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "competitor": {"type": "string"},
                    "kind": {"type": "string"},
                    "summary": {"type": "string"},
                    "observed_date": {"type": "string"},
                    "attributes": {"type": "object", "additionalProperties": {"type": "string"}},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                },
                "required": ["competitor", "summary"],
            },
        }
    },
    "required": ["previous", "current"],
}


class GeminiDeepResearchAdapter:
    """Deep research over the web via Gemini, grounded with Google Search."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.deep_research.model
        self._max_sources = settings.deep_research.max_sources
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Lazy, region-validated client construction
    # ------------------------------------------------------------------ #
    def _get_client(self, market: Market | None = None) -> genai.Client:
        # Validate the residency region BEFORE any network construction.
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google import genai  # noqa: PLC0415 — lazy: gcp profile only

            self._client = genai.Client(
                vertexai=True,
                project=self._settings.project_id,
                location=region,
            )
        return self._client

    # ------------------------------------------------------------------ #
    # ResearchPort
    # ------------------------------------------------------------------ #
    def research(self, query: ResearchQuery) -> ResearchResult:
        """Run grounded deep research for ``query`` and return cited sources + claims."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client(query.market)
        prompt = self._research_prompt(query)
        response = client.models.generate_content(
            model=self._model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_RESEARCH_SCHEMA,
            ),
        )
        return self._to_result(query, response)

    def competitor_snapshots(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]:
        """Return the (previous, current) competitor-move snapshots for the diff engine."""
        from google.genai import types  # noqa: PLC0415

        client = self._get_client(market)
        prompt = self._snapshot_prompt(market, vertical, competitors)
        response = client.models.generate_content(
            model=self._model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_SNAPSHOT_SCHEMA,
            ),
        )
        payload = self._parse(response)
        previous = self._to_moves(payload.get("previous", []), market, vertical)
        current = self._to_moves(payload.get("current", []), market, vertical)
        return previous, current

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _research_prompt(self, query: ResearchQuery) -> str:
        profile = self._settings.market_profile(query.market)
        competitors = ", ".join(query.competitors) if query.competitors else "the main players"
        return (
            "You are a market-intelligence deep-research agent. Research the topic using "
            "Google Search grounding and return ONLY structured JSON matching the schema.\n"
            f"Topic: {query.topic}\n"
            f"Market: {profile.display_name} ({query.market.value}); "
            f"locales: {', '.join(profile.locales)}\n"
            f"Vertical: {query.vertical.value}\n"
            f"Competitors of interest: {competitors}\n"
            f"Return at most {max(query.max_sources, 1)} sources. Every claim must reference "
            "the ids of the sources that support it. Do not invent sources or claims."
        )

    def _snapshot_prompt(
        self, market: Market, vertical: Vertical, competitors: tuple[str, ...]
    ) -> str:
        profile = self._settings.market_profile(market)
        names = ", ".join(competitors) if competitors else "the main competitors"
        kinds = ", ".join(k.value for k in MoveKind)
        return (
            "You are tracking competitor moves for a market-intelligence brief. Using Google "
            "Search grounding, return ONLY structured JSON with a 'previous' (last quarter) and "
            "'current' (this quarter) list of competitor moves.\n"
            f"Market: {profile.display_name} ({market.value})\n"
            f"Vertical: {vertical.value}\n"
            f"Competitors: {names}\n"
            f"Use one of these 'kind' values: {kinds}.\n"
            "Put comparable, tracked fields (e.g. apr, fee, discount_pct) in 'attributes' as "
            "string values so a diff engine can compare them. Do not invent moves."
        )

    # ------------------------------------------------------------------ #
    # Response mapping
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse(response: Any) -> dict[str, Any]:
        raw = getattr(response, "text", "") or "{}"
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _to_result(self, query: ResearchQuery, response: Any) -> ResearchResult:
        payload = self._parse(response)
        sources: list[ResearchSource] = []
        for item in payload.get("sources", [])[: max(query.max_sources, 1)]:
            sources.append(
                ResearchSource(
                    id=str(item.get("id") or item.get("url") or item.get("title") or ""),
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    source_type=SourceType.WEB,
                    publisher=str(item.get("publisher", "")),
                    published_date=item.get("published_date") or None,
                    market=query.market,
                    vertical=query.vertical,
                    snippet=str(item.get("snippet", "")),
                )
            )
        by_id = {s.id: s for s in sources}
        claims: list[Claim] = []
        for item in payload.get("claims", []):
            cited = tuple(
                by_id[sid].to_citation() for sid in item.get("source_ids", []) if sid in by_id
            )
            claims.append(
                Claim(
                    text=str(item.get("text", "")),
                    citations=cited,
                    subject=str(item.get("subject", "")),
                    market=query.market,
                    vertical=query.vertical,
                    confidence=float(item.get("confidence", 0.0) or 0.0),
                )
            )
        return ResearchResult(query=query, sources=tuple(sources), claims=tuple(claims))

    def _to_moves(
        self, raw_moves: list[dict[str, Any]], market: Market, vertical: Vertical
    ) -> tuple[CompetitorMove, ...]:
        moves: list[CompetitorMove] = []
        for item in raw_moves:
            url = str(item.get("source_url", ""))
            citations: tuple[Citation, ...] = ()
            if url:
                citations = (
                    Citation(
                        source_id=url,
                        source_type=SourceType.WEB,
                        title=str(item.get("source_title", "") or url),
                        url=url,
                    ),
                )
            attributes = {str(k): str(v) for k, v in (item.get("attributes", {}) or {}).items()}
            moves.append(
                CompetitorMove(
                    competitor=str(item.get("competitor", "")),
                    kind=self._coerce_kind(item.get("kind")),
                    summary=str(item.get("summary", "")),
                    market=market,
                    vertical=vertical,
                    observed_date=str(item.get("observed_date", "")),
                    attributes=attributes,
                    citations=citations,
                )
            )
        return tuple(moves)

    @staticmethod
    def _coerce_kind(raw: Any) -> MoveKind:
        try:
            return MoveKind(str(raw))
        except ValueError:
            return MoveKind.OTHER
