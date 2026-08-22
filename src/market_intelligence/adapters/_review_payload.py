"""Shared conversion from an escalated market brief to an ``review-kit`` Review payload.

Lives in the adapter layer (not the pure domain) because it depends on the kit. D1 is generic
marketing intelligence over public + aggregate market data and carries no customer PII by design
(C2/C3/C4 are ``n/a`` in the practices audit, and the repo ships no PII-redaction adapter). Even
so, the subject descriptor, summary and citation snippets are scrubbed defensively before they
leave the process (R1 / P-04 boundary): the review console is a shared sink, so should a stray
identifier ever appear in a fictional source snippet it must never reach Hrz7 over the wire; Hrz7
redacts again before its own audit write (defense in depth). The maker (the agent that originated
the brief) and the tenant are asserted here and trusted by Hrz7 because this is an authenticated
S2S caller (per-hop OBO is the deferred next layer).
"""

from __future__ import annotations

import re

from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.models import Citation, MarketBrief, Severity

# Cap the citations carried on the wire: enough to let a reviewer trace the brief without copying
# the entire evidence set into the review console.
_MAX_CITATIONS = 8

# Defensive scrub: this repo has no redaction adapter (no customer PII by design), so the payload
# builder owns a minimal universal pattern set — email, phone, and national-id shapes for the D1
# markets (SG NRIC/FIN, HK id) — applied regardless of the brief's market so a stray identifier in
# a fictional snippet never crosses the wire. Deliberately tight so genuine market data (prices,
# percentages, dates) is not over-masked.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")),
    ("SG_NRIC", re.compile(r"\b[STFGM]\d{7}[A-Z]\b")),
    ("HK_ID", re.compile(r"\b[A-Z]{1,2}\d{6}\(?\d\)?\b")),
)

# Ordered weakest -> strongest so ``max`` picks the brief's most severe signal.
_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


def _redact(text: str) -> str:
    """Mask email/phone/national-id shapes before the wire, then collapse whitespace."""
    redacted = text
    for label, pattern in _PATTERNS:
        redacted = pattern.sub(f"[{label}]", redacted)
    return re.sub(r"\s+", " ", redacted).strip()


def _overall_severity(brief: MarketBrief) -> Severity:
    """The brief's strongest signal — the most severe material competitor move.

    A MarketBrief has no risk band of its own; its consequential signal is the competitor-move
    diff. With no competitor analysis (or no material moves) it has no risk band, so it defaults
    to MEDIUM.
    """
    analysis = brief.competitor_analysis
    if analysis is None:
        return Severity.MEDIUM
    present = [d.severity for d in analysis.diff.material_deltas if d.severity in _SEVERITY_ORDER]
    if not present:
        return Severity.MEDIUM
    return max(present, key=_SEVERITY_ORDER.index)


def _escalated(brief: MarketBrief) -> bool:
    """Mirror the review policy: a HIGH/CRITICAL material move is a hard escalation."""
    return _overall_severity(brief) in (Severity.HIGH, Severity.CRITICAL)


def _kit_citations(brief: MarketBrief) -> tuple[KitCitation, ...]:
    seen: set[str] = set()
    out: list[KitCitation] = []
    for c in _brief_citations(brief):
        if c.source_id in seen:
            continue
        seen.add(c.source_id)
        out.append(KitCitation(source_id=c.source_id, title=c.title, snippet=_redact(c.snippet)))
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def _brief_citations(brief: MarketBrief) -> list[Citation]:
    out: list[Citation] = list(brief.citations)
    for claim in brief.key_claims:
        out.extend(claim.citations)
    return out


def brief_to_review(brief: MarketBrief, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to Hrz7 when a market brief escalates."""
    analysis = brief.competitor_analysis
    material_moves = len(analysis.diff.material_deltas) if analysis is not None else 0
    descriptor = f"Market brief for {brief.topic} ({brief.market.value}/{brief.vertical.value})"
    summary = (
        f"claims={len(brief.key_claims)}; trends={len(brief.trends)}; "
        f"material_moves={material_moves}; sources={len(brief.sources)}"
    )
    severity = _overall_severity(brief)
    return Review(
        action="market_brief:build",
        subject=_redact(descriptor),
        maker=maker,
        tenant=tenant,
        summary=_redact(summary),
        severity=severity.value,
        # Dual control for the strongest bands (a HIGH/CRITICAL competitor move), else single.
        required_approvals=2 if _escalated(brief) else 1,
        sod_group="market-intel-maker-checker",
        case_ref=brief.id,
        citations=_kit_citations(brief),
    )
