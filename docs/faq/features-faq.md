# Features FAQ

For product, compliance, and delivery teams: what this agent does, what is deterministic vs
LLM, and, importantly, where its responsibilities **stop** and a sibling catalog system takes
over. Cross-references: [`README.md`](../../README.md), [`DEMO.md`](../../DEMO.md),
[`SPEC.md`](../../SPEC.md).

### What does Mkt1 actually produce?

A cited **market brief** and a **competitor analysis**. From a market topic and a set of
competitor names, it grounds deep research over public-web sources plus an internal brand
corpus and produces: a market brief with trend findings, and a competitor analysis with a
per-competitor diff and a SWOT, generic across banking and online retail and the JP/AU/SG
markets. Every claim carries a source `Citation`, and both outputs record a WORM
`AuditEvent`.

### What is deterministic vs done by the LLM?

The consequential work is **deterministic and replayable** (pure stdlib, unit-tested): source
deduplication (`dedup_service.py`), the competitor diff (`diff_service.py`), trend scoring
(`trend_service.py`), and the SWOT synthesis (`swot_service.py`). The LLM only **narrates**
the already-computed result (`brief_service`) and classifies or triages. An auditor can
recompute every ranking and finding without the model. This is by design (the "deterministic
domain service" pattern). Empty retrieval is a hard error (`ResearchEmptyError`), never an
ungrounded brief.

### Is anything auto-approved?

No. Every consequential output sets `requires_human_review=True` (maker-checker); the agent
proposes and a qualified human disposes. When review is required the audit decision is
`ESCALATED`, and the escalation is routed to the sibling **Hrz7** human-review console (rule
R8) over S2S with a redact-before-wire payload.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable GRC systems. It **owns** the
market-intelligence and competitor-analysis domain logic and its outputs. It **integrates**
(via the `platform` profile's HTTP adapters) several cross-cutting concerns owned by sibling
platform systems, do not rebuild these in a fork:

| Concern | Owned by (catalog id / repo) | Mkt1's role |
|---|---|---|
| Runtime guardrail: prompt-injection / jailbreak defense, output screening | **Hrz1** `agent-guardrail-gateway` | consumes it around the LLM (input + output screen in `brief_service._guard`) |
| Governed RAG / knowledge base with citations | **Hrz2** `enterprise-knowledge-base` | ingests the brand corpus into it, retrieves grounded passages from it |
| Agent registry, versioning, identity | **Hrz3** `agent-registry` | publishes its A2A AgentCard (`agent/agent_card.py`) for discovery |
| AI-quality / eval / model-risk promotion gate | **Hrz4** `model-quality-gate` | its eval metrics gate promotion; the offline gate mirrors it (bundle `mkt1-market-intel`) |
| Observability + immutable WORM prompt/response audit | **Hrz5** `agent-observability` | writes audit events to it; traces spans through it |
| Human review / maker-checker console | **Hrz7** `human-review-console` | routes `requires_human_review` escalations to it (R8) |
| Regulatory Q&A / control checklists | **Rsk1** `compliance-advisory` | consumes it for compliance checks |

So the guardrail, knowledge base, audit sink, eval platform and review console are
*dependencies*, not features of this repo. Mkt1's dedup / diff / trend / SWOT engines are the
research logic, distinct from the platform's runtime controls.

### Can I use this for a non-market-intelligence research product?

Yes, that is the point of the kernel/vertical split. The reusable core (citations, grounding,
the dedup / diff / trend / SWOT engines, audit, eval, maker-checker) transfers to adjacent
grounded-research verticals. You replace the `MarketBrief` / `CompetitorAnalysis` artifacts
and the prompts and retune the market knobs and taxonomy. See
[`docs/ADOPTING.md`](../ADOPTING.md) and [adoption-faq.md](adoption-faq.md).

### How do I see it working?

`make demo` runs the offline brief flow over the local adapters and renders the audit-first
static HTML; `make demo-server` runs the presenter-controlled offline demo server on port
8110. `make smoke-local` builds a cited brief end to end (`mkt-intel brief ... -m SG -v
banking`). Everything runs on synthetic, fictional data with no cloud and no API key.
