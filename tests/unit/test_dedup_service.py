"""Unit tests for the deterministic claim/source dedup engine."""

from __future__ import annotations

from market_intelligence.domain.dedup_service import ClaimDedupService
from market_intelligence.domain.models import (
    Citation,
    Claim,
    Market,
    ResearchSource,
    SourceType,
    Vertical,
)


def _cit(sid: str, page: int = 1) -> Citation:
    return Citation(source_id=sid, source_type=SourceType.WEB, title=sid, page=page)


def _claim(text: str, sids: tuple[str, ...], subject: str = "Acme", conf: float = 0.5) -> Claim:
    return Claim(
        text=text,
        citations=tuple(_cit(s) for s in sids),
        subject=subject,
        market=Market.SG,
        vertical=Vertical.BANKING,
        confidence=conf,
    )


def test_near_duplicate_claims_merge_and_union_citations():
    svc = ClaimDedupService(similarity_threshold=0.5)
    claims = [
        _claim("Acme Bank raised its savings rate to 4.1 percent", ("a",), conf=0.6),
        _claim("Acme Bank raised the savings rate to 4.1 percent", ("b",), conf=0.9),
    ]
    out = svc.dedup_claims(claims)
    assert len(out) == 1
    assert {c.source_id for c in out[0].citations} == {"a", "b"}
    assert out[0].confidence == 0.9  # max of the group


def test_distinct_subjects_never_merge():
    svc = ClaimDedupService(similarity_threshold=0.1)
    claims = [
        _claim("raised the rate", ("a",), subject="Acme"),
        _claim("raised the rate", ("b",), subject="Merlion"),
    ]
    out = svc.dedup_claims(claims)
    assert len(out) == 2


def test_unrelated_claims_are_kept_separate():
    svc = ClaimDedupService(similarity_threshold=0.6)
    claims = [
        _claim("Acme raised the savings rate", ("a",)),
        _claim("Acme launched a travel rewards card", ("b",)),
    ]
    out = svc.dedup_claims(claims)
    assert len(out) == 2


def test_dedup_sources_by_url_keeps_highest_score():
    svc = ClaimDedupService()
    sources = [
        ResearchSource(id="s1", title="t", url="https://example.test/x", score=0.5),
        ResearchSource(id="s2", title="t", url="https://example.test/x/", score=0.9),
        ResearchSource(id="s3", title="t", url="https://example.test/y", score=0.3),
    ]
    out = svc.dedup_sources(sources)
    assert len(out) == 2
    by_url = {s.url.rstrip("/"): s for s in out}
    assert by_url["https://example.test/x"].score == 0.9


def test_merge_citations_dedups_by_source_and_page():
    cits = (_cit("a", 1), _cit("a", 1), _cit("a", 2), _cit("b", 1))
    merged = ClaimDedupService.merge_citations(cits)
    assert len(merged) == 3


def test_determinism():
    svc = ClaimDedupService()
    claims = [_claim("Acme raised the rate", ("a",)), _claim("Acme raised the rate", ("b",))]
    first = svc.dedup_claims(claims)
    second = svc.dedup_claims(claims)
    assert [c.text for c in first] == [c.text for c in second]
    assert [tuple(x.source_id for x in c.citations) for c in first] == [
        tuple(x.source_id for x in c.citations) for c in second
    ]


def test_default_threshold():
    assert ClaimDedupService().similarity_threshold == 0.6
