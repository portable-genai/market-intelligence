"""Serve the governed tool catalog Mkt3 already declares, over MCP 2026-07-28.

The catalog declared three governed tools and served none of them: there was no MCP server
process anywhere in the fleet. This supplies the callables that answer the existing catalog and
declares nothing new. `hex_service_kit.mcpserve.bind` refuses a mismatch in either direction at
start-up.

`search_internal_corpus` reaches the knowledge-base port directly rather than through the brief
service, because it IS a retrieval and routing it through a brief would run a research pass the
caller did not ask for. The other two are the brief service's own two entry points.

MCP stdio verifies no end user, so the caller is recorded as a SERVICE caller, no tenant is
asserted, and retrieval sees no entitlement principals: the fail-closed filter then admits the
untagged public corpus and nothing else, which is what an unauthenticated transport should get.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit import mcpserve

from ..config import build_container
from ..domain.models import BriefRequest, Market, RetrievalQuery, Vertical

#: The tools this module answers, as data, so a test can hold it against the catalog.
HANDLER_NAMES: tuple[str, ...] = ("deep_research", "search_internal_corpus", "competitor_analysis")


def _optional_market(arguments: dict[str, Any]) -> Market | None:
    """The requested market, or None when the caller named none. Never a guessed default."""
    raw = str(arguments.get("market", "") or "")
    return Market(raw) if raw else None


def _optional_vertical(arguments: dict[str, Any]) -> Vertical | None:
    raw = str(arguments.get("vertical", "") or "")
    return Vertical(raw) if raw else None


def _request(arguments: dict[str, Any]) -> BriefRequest:
    return BriefRequest(
        topic=str(arguments.get("topic", "") or ""),
        market=Market(str(arguments.get("market", ""))),
        vertical=Vertical(str(arguments.get("vertical", ""))),
        max_sources=int(arguments.get("max_sources") or 8),
    )


def build_handlers(actor: str) -> dict[str, mcpserve.Handler]:
    """Bind each declared tool to the service or port that already performs it."""
    from ..api.app import make_brief_service

    def deep_research(**arguments: Any) -> Any:
        return make_brief_service().build_brief(_request(arguments), actor=actor)

    def competitor_analysis(**arguments: Any) -> Any:
        return make_brief_service().competitor_analysis(_request(arguments), actor=actor)

    def search_internal_corpus(**arguments: Any) -> Any:
        # The scope is PASSED, not merely declared. This tool advertised `market` and
        # `vertical` in its schema and then built an unscoped RetrievalQuery, so a caller
        # asking for one market's corpus was served every market's -- the declaration was the
        # only thing that was ever scoped. `RetrievalQuery` has carried both fields all along.
        # An absent value stays None, which is the port's own "no partition" and a different
        # thing from a value the caller chose.
        return build_container().knowledge_base.search(
            RetrievalQuery(
                text=str(arguments.get("query", "") or ""),
                top_k=int(arguments.get("top_k") or 5),
                market=_optional_market(arguments),
                vertical=_optional_vertical(arguments),
            )
        )

    return {
        "deep_research": deep_research,
        "search_internal_corpus": search_internal_corpus,
        "competitor_analysis": competitor_analysis,
    }


def build_server(actor: str, *, with_audit_tools: bool = True) -> Any:
    """Build the MCP server for Mkt3's catalog, refusing on any catalog/handler mismatch."""
    container = build_container()
    return mcpserve.build_server(
        name="market-intelligence",
        version=str(getattr(container.settings, "version", "") or "0.0.1"),
        catalog=container.tool_catalog,
        handlers=build_handlers(actor),
        audit_store=getattr(container, "audit", None) if with_audit_tools else None,
    )
