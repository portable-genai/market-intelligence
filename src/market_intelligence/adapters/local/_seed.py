"""Built-in, OBVIOUSLY-FICTIONAL synthetic seed for the ``local`` profile.

This is the offline corpus that makes a local run grounded out of the box: market /
competitor research passages, deep-research sources + claims, and competitor-move
snapshots, spanning BOTH verticals (banking AND online retail) across ALL THREE markets
(JP, AU, SG). Every company name is invented (suffixed FICTIONAL) and every URL points at
``example.test``; nothing here is real data.

The data is keyed by (market, vertical) so the local ResearchPort and KnowledgeBasePort
serve vertical- and market-specific evidence, proving D1 is generic and APAC without any
hard-coded branch in the engines.
"""

from __future__ import annotations

from ...domain.models import (
    Citation,
    Claim,
    CompetitorMove,
    Market,
    MoveKind,
    ResearchSource,
    RetrievedPassage,
    SourceType,
    Vertical,
)

_Key = tuple[Market, Vertical]


def _cit(sid: str, title: str, page: int, date: str) -> Citation:
    return Citation(
        source_id=sid,
        source_type=SourceType.WEB,
        title=title,
        url=f"https://example.test/{sid}",
        page=page,
        published_date=date,
        snippet=f"{title} (FICTIONAL synthetic source).",
        score=0.9,
    )


# --------------------------------------------------------------------------- #
# Deep-research sources + claims, per (market, vertical)
# --------------------------------------------------------------------------- #
RESEARCH_SOURCES: dict[_Key, tuple[ResearchSource, ...]] = {
    (Market.SG, Vertical.BANKING): (
        ResearchSource(
            id="sg-bank-src-1",
            title="Acme Bank SG raises savings APR (FICTIONAL)",
            url="https://example.test/sg-bank-src-1",
            source_type=SourceType.NEWS,
            publisher="Lion City Wire (FICTIONAL)",
            published_date="2026-06-01",
            market=Market.SG,
            vertical=Vertical.BANKING,
            snippet="Acme Bank SG lifts its flagship savings APR to 4.10 percent.",
            score=0.92,
        ),
        ResearchSource(
            id="sg-bank-src-2",
            title="Merlion Digital Bank waives account fees (FICTIONAL)",
            url="https://example.test/sg-bank-src-2",
            source_type=SourceType.NEWS,
            publisher="Harbour Finance Daily (FICTIONAL)",
            published_date="2026-05-20",
            market=Market.SG,
            vertical=Vertical.BANKING,
            snippet="Merlion Digital Bank scraps monthly account fees for under-30s.",
            score=0.88,
        ),
    ),
    (Market.JP, Vertical.BANKING): (
        ResearchSource(
            id="jp-bank-src-1",
            title="Sakura Neobank launches yen FX wallet (FICTIONAL)",
            url="https://example.test/jp-bank-src-1",
            source_type=SourceType.NEWS,
            publisher="Tokyo Ledger (FICTIONAL)",
            published_date="2026-06-05",
            market=Market.JP,
            vertical=Vertical.BANKING,
            snippet="Sakura Neobank launches a multi-currency yen FX wallet.",
            score=0.9,
        ),
    ),
    (Market.AU, Vertical.BANKING): (
        ResearchSource(
            id="au-bank-src-1",
            title="Outback Mutual cuts home-loan rate (FICTIONAL)",
            url="https://example.test/au-bank-src-1",
            source_type=SourceType.NEWS,
            publisher="Southern Cross Money (FICTIONAL)",
            published_date="2026-06-02",
            market=Market.AU,
            vertical=Vertical.BANKING,
            snippet="Outback Mutual trims its variable home-loan rate by 15 bps.",
            score=0.91,
        ),
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): (
        ResearchSource(
            id="sg-retail-src-1",
            title="ShopMerlion offers free next-day delivery (FICTIONAL)",
            url="https://example.test/sg-retail-src-1",
            source_type=SourceType.NEWS,
            publisher="Harbour Commerce Weekly (FICTIONAL)",
            published_date="2026-06-03",
            market=Market.SG,
            vertical=Vertical.ONLINE_RETAIL,
            snippet="ShopMerlion rolls out free next-day delivery island-wide.",
            score=0.9,
        ),
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): (
        ResearchSource(
            id="jp-retail-src-1",
            title="MidoriMart launches a points loyalty tier (FICTIONAL)",
            url="https://example.test/jp-retail-src-1",
            source_type=SourceType.NEWS,
            publisher="Tokyo Retail Digest (FICTIONAL)",
            published_date="2026-06-04",
            market=Market.JP,
            vertical=Vertical.ONLINE_RETAIL,
            snippet="MidoriMart introduces a tiered points loyalty programme.",
            score=0.89,
        ),
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): (
        ResearchSource(
            id="au-retail-src-1",
            title="BoomerangBuy adds buy-now-pay-later (FICTIONAL)",
            url="https://example.test/au-retail-src-1",
            source_type=SourceType.NEWS,
            publisher="Southern Cross Commerce (FICTIONAL)",
            published_date="2026-06-06",
            market=Market.AU,
            vertical=Vertical.ONLINE_RETAIL,
            snippet="BoomerangBuy adds an in-checkout buy-now-pay-later option.",
            score=0.9,
        ),
    ),
}


def _claims_for(key: _Key) -> tuple[Claim, ...]:
    market, vertical = key
    out: list[Claim] = []
    for src in RESEARCH_SOURCES.get(key, ()):  # one claim per source, cited
        out.append(
            Claim(
                text=src.snippet,
                citations=(src.to_citation(),),
                subject=src.publisher.split(" ")[0],
                market=market,
                vertical=vertical,
                confidence=src.score,
            )
        )
    return tuple(out)


RESEARCH_CLAIMS: dict[_Key, tuple[Claim, ...]] = {key: _claims_for(key) for key in RESEARCH_SOURCES}


# --------------------------------------------------------------------------- #
# Competitor-move snapshots (previous, current) per (market, vertical)
# --------------------------------------------------------------------------- #
COMPETITOR_SNAPSHOTS: dict[_Key, tuple[tuple[CompetitorMove, ...], tuple[CompetitorMove, ...]]] = {
    (Market.SG, Vertical.BANKING): (
        (
            CompetitorMove(
                competitor="Acme Bank SG (FICTIONAL)",
                kind=MoveKind.RATE_CHANGE,
                summary="Flagship savings APR",
                market=Market.SG,
                vertical=Vertical.BANKING,
                observed_date="2026-05-01",
                attributes={"apr": "3.80"},
                citations=(_cit("sg-bank-src-1", "Acme Bank SG savings APR", 1, "2026-05-01"),),
            ),
        ),
        (
            CompetitorMove(
                competitor="Acme Bank SG (FICTIONAL)",
                kind=MoveKind.RATE_CHANGE,
                summary="Flagship savings APR",
                market=Market.SG,
                vertical=Vertical.BANKING,
                observed_date="2026-06-01",
                attributes={"apr": "4.10"},
                citations=(_cit("sg-bank-src-1", "Acme Bank SG savings APR", 1, "2026-06-01"),),
            ),
            CompetitorMove(
                competitor="Merlion Digital Bank (FICTIONAL)",
                kind=MoveKind.FEE_CHANGE,
                summary="Monthly account fee for under-30s",
                market=Market.SG,
                vertical=Vertical.BANKING,
                observed_date="2026-05-20",
                attributes={"monthly_fee": "0.00"},
                citations=(_cit("sg-bank-src-2", "Merlion fee waiver", 1, "2026-05-20"),),
            ),
        ),
    ),
    (Market.JP, Vertical.BANKING): (
        (),
        (
            CompetitorMove(
                competitor="Sakura Neobank (FICTIONAL)",
                kind=MoveKind.PRODUCT_LAUNCH,
                summary="Multi-currency yen FX wallet",
                market=Market.JP,
                vertical=Vertical.BANKING,
                observed_date="2026-06-05",
                attributes={"currencies": "12"},
                citations=(_cit("jp-bank-src-1", "Sakura FX wallet", 1, "2026-06-05"),),
            ),
        ),
    ),
    (Market.AU, Vertical.BANKING): (
        (
            CompetitorMove(
                competitor="Outback Mutual (FICTIONAL)",
                kind=MoveKind.RATE_CHANGE,
                summary="Variable home-loan rate",
                market=Market.AU,
                vertical=Vertical.BANKING,
                observed_date="2026-05-02",
                attributes={"rate": "6.20"},
                citations=(_cit("au-bank-src-1", "Outback home-loan rate", 1, "2026-05-02"),),
            ),
        ),
        (
            CompetitorMove(
                competitor="Outback Mutual (FICTIONAL)",
                kind=MoveKind.RATE_CHANGE,
                summary="Variable home-loan rate",
                market=Market.AU,
                vertical=Vertical.BANKING,
                observed_date="2026-06-02",
                attributes={"rate": "6.05"},
                citations=(_cit("au-bank-src-1", "Outback home-loan rate", 1, "2026-06-02"),),
            ),
        ),
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): (
        (),
        (
            CompetitorMove(
                competitor="ShopMerlion (FICTIONAL)",
                kind=MoveKind.PROMOTION,
                summary="Free next-day delivery island-wide",
                market=Market.SG,
                vertical=Vertical.ONLINE_RETAIL,
                observed_date="2026-06-03",
                attributes={"delivery_fee": "0.00", "sla_days": "1"},
                citations=(_cit("sg-retail-src-1", "ShopMerlion delivery", 1, "2026-06-03"),),
            ),
        ),
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): (
        (),
        (
            CompetitorMove(
                competitor="MidoriMart (FICTIONAL)",
                kind=MoveKind.CAMPAIGN,
                summary="Tiered points loyalty programme",
                market=Market.JP,
                vertical=Vertical.ONLINE_RETAIL,
                observed_date="2026-06-04",
                attributes={"tiers": "3", "max_points_pct": "5"},
                citations=(_cit("jp-retail-src-1", "MidoriMart loyalty", 1, "2026-06-04"),),
            ),
        ),
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): (
        (),
        (
            CompetitorMove(
                competitor="BoomerangBuy (FICTIONAL)",
                kind=MoveKind.PRODUCT_LAUNCH,
                summary="In-checkout buy-now-pay-later",
                market=Market.AU,
                vertical=Vertical.ONLINE_RETAIL,
                observed_date="2026-06-06",
                attributes={"provider": "PayLaterCo", "installments": "4"},
                citations=(_cit("au-retail-src-1", "BoomerangBuy BNPL", 1, "2026-06-06"),),
            ),
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Internal research corpus passages (the brand / internal-research store, A2)
# --------------------------------------------------------------------------- #
def _corpus_passages() -> tuple[RetrievedPassage, ...]:
    passages: list[RetrievedPassage] = []
    for (market, vertical), sources in RESEARCH_SOURCES.items():
        for src in sources:
            tag_m = market.value
            tag_v = vertical.value
            passages.append(
                RetrievedPassage(
                    text=(
                        f"Internal research note ({tag_m}/{tag_v}, FICTIONAL): {src.snippet} "
                        "Our team should track this competitor move."
                    ),
                    citation=Citation(
                        source_id=f"internal-{src.id}",
                        source_type=SourceType.INTERNAL,
                        title=f"Internal note on {src.title}",
                        url=f"https://corpus.example.test/internal-{src.id}",
                        page=1,
                        published_date=src.published_date,
                        snippet=src.snippet,
                        score=0.8,
                    ),
                    score=0.8,
                    tags=(f"market:{tag_m}", f"vertical:{tag_v}"),
                )
            )
    return tuple(passages)


CORPUS_PASSAGES: tuple[RetrievedPassage, ...] = _corpus_passages()
