"""KnowledgeBasePort — the internal research / brand corpus (File Search).

D1 grounds the brief on BOTH external deep research (ResearchPort) AND an internal
research corpus: prior market reports, the brand book and internal competitor notes. The
primary GCP adapter is **File Search / Agent Search** over that corpus; the ``platform``
adapter is a thin HTTP client to the shared A2 Enterprise Knowledge Base; the local
adapter is an in-process SQLite FTS5 index over the seeded fictional corpus.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RetrievalQuery, RetrievedPassage


@runtime_checkable
class KnowledgeBasePort(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievedPassage]:
        """Retrieve ranked passages from the internal corpus for grounding the brief."""
        ...
