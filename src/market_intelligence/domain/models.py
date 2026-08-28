"""Domain models for the Market Intelligence and Competitor Analysis system (D1).

This module is the heart of the hexagon. It has **no dependency on Google Cloud,
ADK, FastAPI, or any framework** (only the Python standard library). Every adapter
(GCP, remote-platform, or on-prem placeholder) speaks in terms of these types, which
is what lets the managed-service stack be swapped for an on-premise one without
touching domain logic (no vendor lock-in, ports and adapters).

D1 is deliberately **generic marketing intelligence**, not a bank-specific tool:

* ``Vertical`` is a configurable enum (banking, online retail), so the same engines
  reason over a deposit-account competitor move and an e-commerce free-shipping promo.
* ``Market`` is a configurable enum (JP, AU, SG) carrying its residency region and
  locales, so JP, AU and SG are first-class config and seed, never hard-coded.

The deterministic engines are the heart of the system: source/claim dedup and
provenance, competitor-move diff, trend scoring, and SWOT / where-to-play synthesis.
The LLM only narrates and drafts; every claim that leaves the system carries a
:class:`Citation` and every consequential aggregate sets ``requires_human_review``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# The shared value types, imported rather than redeclared. ``agent_eval_kit.report`` is the
# SUBMODULE on purpose: the package root pulls in ``gate_client``, which imports httpx, and this
# module promises to be standard-library-only so the domain core stays framework-free.
from agent_eval_kit.report import EvalMetricResult as EvalMetricResult
from agent_eval_kit.report import EvalReport as EvalReport
from hex_service_kit import StrEnum
from hex_service_kit.observability import TokenUsage

from .kernel import ThinkingLevel


def utcnow() -> datetime:
    """Timezone-aware UTC now (the single clock the domain uses)."""
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Vertical and Market — the two configurable axes (generic, multi-vertical, APAC)
# --------------------------------------------------------------------------- #
class Vertical(StrEnum):
    """The business vertical the brief is scoped to.

    D1 is generic: banking is ONE vertical and online retail is another. The
    deterministic engines and the LLM prompts switch taxonomy/rules by vertical; no
    bank-only logic is baked into the domain.
    """

    BANKING = "banking"
    ONLINE_RETAIL = "online_retail"


class Market(StrEnum):
    """A supported market (Japan, Australia, Singapore).

    The residency region, locales and per-market rule sets are config + seed (see
    :data:`MARKET_PROFILES` and ``config/settings.yaml``), never hard-coded into a
    branch. Adding a market is a config + seed change, not a code change.
    """

    JP = "JP"
    AU = "AU"
    SG = "SG"


@dataclass(frozen=True, slots=True)
class MarketProfile:
    """Static, fictional-data-friendly metadata for a market.

    The residency ``region`` is a GCP regional id selectable at deploy and validated;
    ``locales`` drives bilingual (ja + en) output. These defaults can be overridden in
    ``config/settings.yaml`` so the catalog stays config-driven.
    """

    market: Market
    region: str  # GCP residency region, e.g. "asia-northeast1" (Tokyo)
    display_name: str
    locales: tuple[str, ...]  # e.g. ("ja", "en") or ("en",)
    currency: str = ""


# Built-in defaults. Region/locale are config + seed: settings.yaml may override these.
MARKET_PROFILES: dict[Market, MarketProfile] = {
    Market.JP: MarketProfile(
        market=Market.JP,
        region="asia-northeast1",
        display_name="Japan",
        locales=("ja", "en"),
        currency="JPY",
    ),
    Market.AU: MarketProfile(
        market=Market.AU,
        region="australia-southeast1",
        display_name="Australia",
        locales=("en",),
        currency="AUD",
    ),
    Market.SG: MarketProfile(
        market=Market.SG,
        region="asia-southeast1",
        display_name="Singapore",
        locales=("en",),
        currency="SGD",
    ),
}


# --------------------------------------------------------------------------- #
# Provenance / citation
# --------------------------------------------------------------------------- #
class SourceType(StrEnum):
    """Every citation names which kind of evidence it points to."""

    WEB = "web"  # a public-web deep-research / grounded source
    INTERNAL = "internal"  # the internal brand / research corpus (File Search)
    FILING = "filing"  # a competitor public filing / disclosure
    NEWS = "news"  # a news / trade-press article
    REPORT = "report"  # an analyst / industry report
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Citation:
    """Provenance attached to every claim and finding in a brief.

    A strategist must be able to trace every statement, number and competitor move back
    to its exact source: an auditable market brief is the whole point of D1.
    """

    source_id: str
    source_type: SourceType
    title: str
    url: str = ""
    page: int | None = None
    published_date: str | None = None  # ISO date as published, if known
    snippet: str = ""
    score: float | None = None


# --------------------------------------------------------------------------- #
# Research sources, claims and passages
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ResearchSource:
    """One source surfaced by deep research / web grounding or internal retrieval."""

    id: str
    title: str
    url: str
    source_type: SourceType = SourceType.WEB
    publisher: str = ""
    published_date: str | None = None
    market: Market | None = None
    vertical: Vertical | None = None
    snippet: str = ""
    score: float = 0.0

    def to_citation(self) -> Citation:
        return Citation(
            source_id=self.id,
            source_type=self.source_type,
            title=self.title,
            url=self.url,
            published_date=self.published_date,
            snippet=self.snippet,
            score=self.score,
        )


@dataclass(frozen=True, slots=True)
class Claim:
    """A single atomic claim extracted from research, carrying its provenance.

    The dedup engine collapses near-duplicate claims across sources, merging their
    citations so one finding cites every source that corroborates it.
    """

    text: str
    citations: tuple[Citation, ...] = ()
    subject: str = ""  # the competitor / topic the claim is about
    market: Market | None = None
    vertical: Vertical | None = None
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """A passage retrieved from the internal research corpus (KnowledgeBasePort)."""

    text: str
    citation: Citation
    score: float = 0.0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    top_k: int = 10
    market: Market | None = None
    vertical: Vertical | None = None
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResearchQuery:
    """A deep-research request scoped to a topic, market and vertical."""

    topic: str
    market: Market
    vertical: Vertical
    max_sources: int = 12
    competitors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """The raw output of a deep-research run: sources and extracted claims."""

    query: ResearchQuery
    sources: tuple[ResearchSource, ...] = ()
    claims: tuple[Claim, ...] = ()


# --------------------------------------------------------------------------- #
# Generation (LLM) — the LLM only narrates / drafts; never decides the numbers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class WebCitation:
    """Provenance for a public-web grounded fact returned by the model."""

    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str  # "user" | "model" | "system"
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    messages: tuple[LlmMessage, ...]
    system_instruction: str | None = None
    model: str | None = None  # None => adapter default from config
    thinking: ThinkingLevel = ThinkingLevel.MEDIUM
    temperature: float = 0.0  # omitted at a call site means this value; it must not sample
    max_output_tokens: int = 4096
    response_schema: dict | None = None  # JSON schema for structured output


# TokenUsage is NOT declared here. It is re-exported from ``hex_service_kit.observability``
# at the top of this module, because sixteen repositories had each hand-copied the same three
# int fields and a value type copied N times is N types that drift. This one had not drifted
# yet; re-exporting is what stops it from ever doing so.


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    web_citations: tuple[WebCitation, ...] = ()
    raw: dict | None = None


# --------------------------------------------------------------------------- #
# Safety (guardrail) — A1 Guardrail Gateway concern
# --------------------------------------------------------------------------- #
class GuardrailCategory(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    SENSITIVE_DATA = "sensitive_data"
    MALICIOUS_URL = "malicious_url"
    OTHER = "other"


class Direction(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class GuardrailFinding:
    category: GuardrailCategory
    confidence: str  # "low" | "medium" | "high"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    direction: Direction
    findings: tuple[GuardrailFinding, ...] = ()
    sanitized_text: str | None = None
    reason: str = ""


# --------------------------------------------------------------------------- #
# Audit and observability — A5 Observability, Audit and FinOps concern
# --------------------------------------------------------------------------- #
class Decision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"  # routed to a human (maker-checker)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable, WORM-stored record of one market-intelligence interaction."""

    action: str  # "market_brief" | "competitor_analysis" | "research"
    actor: str  # authenticated analyst / service identity
    decision: Decision
    prompt: str = ""
    response: str = ""
    citations: tuple[Citation, ...] = ()
    resource: str = "market-intelligence"
    trace_id: str | None = None
    timestamp: datetime = field(default_factory=utcnow)
    metadata: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Evaluation gate — A4 AI Quality and Model-Risk concern
# --------------------------------------------------------------------------- #
# EvalMetricResult and EvalReport are NOT declared here either; they are re-exported from
# ``agent_eval_kit.report`` at the top of this module. The commons EvalReport is a strict
# SUPERSET of a locally declared three-field report: it adds run_id, dataset_version,
# dataset_digest, evaluator, schema_version, trace_id, correlation_id, artifact_refs and
# attested, all defaulted, so every existing constructor still compiles. Its ``passed`` rule
# is the same fail-closed one, character for character:
#
#     self.n_examples > 0 and bool(self.results) and all(r.passed for r in self.results)
#
# which matters more than the fields. ``all(())`` is vacuously true, so a report that scored
# nothing would certify a promotion; ``eval/run_eval.py`` exits on this property. Sharing the
# type is only safe because the guard came with it.


# --------------------------------------------------------------------------- #
# Governance — A3 Agent Registry and the MCP tool catalog
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AgentSkill:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Minimal A2A-style agent card published at /.well-known/agent-card.json."""

    name: str
    description: str
    url: str
    version: str
    skills: tuple[AgentSkill, ...] = ()
    provider: str = "market-intelligence"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A governed, least-privilege tool exposed to the agent (typically via MCP)."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Shared severity / impact scales
# --------------------------------------------------------------------------- #
class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# 1. Competitor moves and the competitor-move diff
# --------------------------------------------------------------------------- #
class MoveKind(StrEnum):
    """A category of competitor move (generic across verticals).

    Banking and online retail share these abstract kinds; per-vertical taxonomy detail
    lives in the seed data, not in the enum, so the engine stays generic.
    """

    PRODUCT_LAUNCH = "product_launch"
    PRICING_CHANGE = "pricing_change"
    PROMOTION = "promotion"
    FEE_CHANGE = "fee_change"
    RATE_CHANGE = "rate_change"
    PARTNERSHIP = "partnership"
    CAMPAIGN = "campaign"
    EXPANSION = "expansion"
    OTHER = "other"


class MoveStatus(StrEnum):
    """How a move changed between two competitor snapshots (the diff outcome)."""

    NEW = "new"  # appeared in the current snapshot only
    CHANGED = "changed"  # present in both but a tracked attribute moved
    WITHDRAWN = "withdrawn"  # present previously, gone now
    UNCHANGED = "unchanged"  # present in both, unchanged


@dataclass(frozen=True, slots=True)
class CompetitorMove:
    """One observed competitor action at a point in time.

    ``attributes`` holds the tracked, comparable fields (e.g. ``{"apr": "4.50"}`` for
    banking or ``{"discount_pct": "15"}`` for retail). The diff engine compares these.
    """

    competitor: str
    kind: MoveKind
    summary: str
    market: Market
    vertical: Vertical
    observed_date: str = ""  # ISO date the move was observed
    attributes: dict[str, str] = field(default_factory=dict)
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class MoveDelta:
    """One entry in a competitor-move diff: what changed and why it matters."""

    id: str  # stable, deterministic id (competitor:kind:summary slug)
    competitor: str
    kind: MoveKind
    status: MoveStatus
    summary: str
    changed_fields: tuple[str, ...] = ()
    before: dict[str, str] = field(default_factory=dict)
    after: dict[str, str] = field(default_factory=dict)
    severity: Severity = Severity.MEDIUM
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class CompetitorDiff:
    """The deterministic diff between a previous and current set of competitor moves."""

    market: Market
    vertical: Vertical
    deltas: tuple[MoveDelta, ...] = ()

    @property
    def material_deltas(self) -> tuple[MoveDelta, ...]:
        """Deltas that actually changed the picture (not UNCHANGED)."""
        return tuple(d for d in self.deltas if d.status is not MoveStatus.UNCHANGED)

    @property
    def requires_human_review(self) -> bool:
        """A material competitor diff is consequential: a human strategist signs off."""
        return any(d.severity in (Severity.HIGH, Severity.CRITICAL) for d in self.material_deltas)


# --------------------------------------------------------------------------- #
# 2. Trend scoring
# --------------------------------------------------------------------------- #
class TrendDirection(StrEnum):
    RISING = "rising"
    STEADY = "steady"
    FADING = "fading"


@dataclass(frozen=True, slots=True)
class TrendSignal:
    """One observation contributing to a trend (a dated mention with provenance)."""

    topic: str
    observed_date: str  # ISO date
    weight: float = 1.0
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class TrendScore:
    """A deterministic trend score for a topic, with the inputs that produced it."""

    topic: str
    market: Market
    vertical: Vertical
    score: float  # 0..1 normalised momentum
    direction: TrendDirection
    mentions: int = 0
    distinct_sources: int = 0
    rationale: str = ""
    citations: tuple[Citation, ...] = ()


# --------------------------------------------------------------------------- #
# 3. SWOT / where-to-play synthesis
# --------------------------------------------------------------------------- #
class SwotKind(StrEnum):
    STRENGTH = "strength"
    WEAKNESS = "weakness"
    OPPORTUNITY = "opportunity"
    THREAT = "threat"


@dataclass(frozen=True, slots=True)
class SwotItem:
    """One cited SWOT entry derived deterministically from the evidence."""

    kind: SwotKind
    statement: str
    weight: float = 0.0
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class WhereToPlayOption:
    """A scored, ranked where-to-play option (a segment / move to consider).

    The score is deterministic (attractiveness x right-to-win); the LLM only narrates
    the rationale. Nothing here auto-executes: a strategist chooses.
    """

    id: str
    title: str
    attractiveness: float  # 0..1 deterministic
    right_to_win: float  # 0..1 deterministic
    score: float  # 0..1 combined, deterministic
    rationale: str = ""
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class SwotSynthesis:
    """The SWOT + ranked where-to-play options for a market/vertical."""

    market: Market
    vertical: Vertical
    items: tuple[SwotItem, ...] = ()
    options: tuple[WhereToPlayOption, ...] = ()

    def by_kind(self, kind: SwotKind) -> tuple[SwotItem, ...]:
        return tuple(i for i in self.items if i.kind is kind)


# --------------------------------------------------------------------------- #
# The aggregates (top-level artifacts) — always require human review
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class BriefRequest:
    """The inbound request for a market brief."""

    topic: str
    market: Market
    vertical: Vertical
    competitors: tuple[str, ...] = ()
    max_sources: int = 12


@dataclass(frozen=True, slots=True)
class CompetitorAnalysis:
    """A cited competitor analysis: the move diff plus the SWOT synthesis.

    Consequential strategy input, so it always requires human review (maker-checker):
    the agent proposes; a qualified strategist disposes before it is relied upon.
    """

    market: Market
    vertical: Vertical
    competitors: tuple[str, ...]
    diff: CompetitorDiff
    swot: SwotSynthesis
    narrative: str = ""
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True
    generated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class MarketBrief:
    """A single cited market brief bundling every artifact for a topic.

    The top-level consequential output of D1. It is strategy input, so it **always**
    requires human review (maker-checker): a maker (the agent) proposes and a checker
    (a qualified strategist) disposes before anyone acts on it.
    """

    id: str
    topic: str
    market: Market
    vertical: Vertical
    summary: str
    key_claims: tuple[Claim, ...] = ()
    trends: tuple[TrendScore, ...] = ()
    competitor_analysis: CompetitorAnalysis | None = None
    sources: tuple[ResearchSource, ...] = ()
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True
    generated_at: datetime = field(default_factory=utcnow)
