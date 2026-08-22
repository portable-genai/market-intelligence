"""LlmPort — LLM text/reasoning for narrating and drafting the brief.

Primary GCP adapter: Gemini models on the Gemini Enterprise Agent Platform
(``gemini-3.5-flash`` for narration, ``gemini-3.1-flash-lite`` for triage). The LLM only
narrates and drafts over the already-computed deterministic result; it never decides the
numbers, the diff, the scores or the ranking.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import LlmRequest, LlmResponse


@runtime_checkable
class LlmPort(Protocol):
    def generate(self, request: LlmRequest) -> LlmResponse:
        """Generate a completion for ``request`` using the configured model."""
        ...

    def classify(self, text: str, labels: list[str]) -> str:
        """Cheap single-label classification (triage/routing tier model)."""
        ...
