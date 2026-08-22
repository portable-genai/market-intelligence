"""ClaimDedupService — deterministic source/claim dedup + provenance merge.

The first deterministic engine in the D1 pipeline (see the ``deterministic-domain-service``
skill): pure, stdlib-only, replayable. Deep research and the internal corpus surface the
same fact from several sources; this engine collapses near-duplicate claims into one
canonical claim whose citations are the union of every corroborating source, so a finding
in the brief cites all of its evidence and the source list carries no duplicate URLs.

Determinism: same inputs -> same output. No LLM, no clock, no network, no randomness. The
LLM never decides which claims are duplicates; this engine does, by a transparent
token-overlap (Jaccard) similarity over a normalised bag of words, with the threshold a
tunable field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Citation, Claim, ResearchSource

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Common words carry no discriminating signal for near-duplicate detection.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True, slots=True)
class ClaimDedupService:
    """Pure, deterministic claim/source dedup with provenance merge.

    ``similarity_threshold`` and ``min_tokens`` are tunables, not magic numbers.
    """

    similarity_threshold: float = 0.6
    min_tokens: int = 1

    def dedup_sources(
        self, sources: tuple[ResearchSource, ...] | list[ResearchSource]
    ) -> tuple[ResearchSource, ...]:
        """Drop duplicate sources by normalised URL (else id), keeping first-seen order.

        The highest-scoring instance of a duplicate URL is retained so the surviving
        source carries the best relevance score.
        """
        best: dict[str, ResearchSource] = {}
        order: list[str] = []
        for s in sources:
            key = self._source_key(s)
            if key not in best:
                best[key] = s
                order.append(key)
            elif s.score > best[key].score:
                best[key] = s
        return tuple(best[k] for k in order)

    def dedup_claims(self, claims: tuple[Claim, ...] | list[Claim]) -> tuple[Claim, ...]:
        """Collapse near-duplicate claims, merging citations from every corroborator.

        Two claims are duplicates when they share a subject and their normalised token
        sets exceed ``similarity_threshold`` by Jaccard overlap. The canonical claim is
        the first-seen text; its citations are the de-duplicated union across the group,
        and its confidence is the max of the group (more corroboration, not less).
        """
        canonical: list[Claim] = []
        canonical_tokens: list[frozenset[str]] = []
        for claim in claims:
            toks = _tokens(claim.text)
            match_idx = self._find_match(claim, toks, canonical, canonical_tokens)
            if match_idx is None:
                canonical.append(claim)
                canonical_tokens.append(toks)
            else:
                canonical[match_idx] = self._merge(canonical[match_idx], claim)
        return tuple(canonical)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _source_key(source: ResearchSource) -> str:
        url = (source.url or "").strip().lower().rstrip("/")
        return url or f"id:{source.id}"

    def _find_match(
        self,
        claim: Claim,
        toks: frozenset[str],
        canonical: list[Claim],
        canonical_tokens: list[frozenset[str]],
    ) -> int | None:
        if len(toks) < self.min_tokens:
            return None
        for idx, existing in enumerate(canonical):
            if existing.subject != claim.subject:
                continue
            if _jaccard(canonical_tokens[idx], toks) >= self.similarity_threshold:
                return idx
        return None

    @staticmethod
    def _merge(canonical: Claim, other: Claim) -> Claim:
        merged_citations = ClaimDedupService.merge_citations(canonical.citations + other.citations)
        return Claim(
            text=canonical.text,
            citations=merged_citations,
            subject=canonical.subject,
            market=canonical.market,
            vertical=canonical.vertical,
            confidence=max(canonical.confidence, other.confidence),
        )

    @staticmethod
    def merge_citations(citations: tuple[Citation, ...]) -> tuple[Citation, ...]:
        """De-duplicate citations by (source_id, page), keeping first-seen order."""
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for c in citations:
            key = (c.source_id, c.page)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return tuple(out)
