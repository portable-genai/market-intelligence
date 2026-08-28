# COMPLIANCE: Mkt1 Market Intelligence and Competitor Analysis

This maps every General Principle (P-01..P-13) and dependency rule (R1..R8) to a concrete
control in **this** repo. Where a principle does not apply to Mkt1, it is marked **n/a** with
the reason. Mkt1 processes public and aggregate market data and **no customer PII**, so its
load-bearing controls are grounding, provenance, maker-checker and audit rather than
data-subject protection.

> The market, competitor and corpus data in `tests/`, `eval/` and the local seed is
> **fictional**. This build is a reference piece and is **not** intended for live use without
> your own legal, security and model-risk sign-off.

---

## General Principles

| # | Principle | How Mkt1 implements it | Evidence |
|---|-----------|----------------------|----------|
| **P-01** | Managed-first, minimal surface | Only the managed services the pinned stack uses are enabled; the agent is hosted on Agent Runtime | `infra/terraform/apis.tf`, `agent/root_agent.py` |
| **P-02** | No vendor lock-in (ports and adapters) | Domain depends only on `Protocol` ports; a profile switch rebinds adapters with no domain change. The `local` family proves the same domain runs entirely off-cloud (SQLite FTS5, deterministic deep-research synthesiser and LLM, no Google Cloud SDK) | `ports/`, `config.py`, `adapters/local/*`, `adapters/onprem/*` |
| **P-03** | Data residency (in-country) | **PARTIAL, and the gap is Agent Search.** Region selected at deploy from a residency allowlist, with per-market overrides (JP asia-northeast1, AU australia-southeast1, SG asia-southeast1), validated to fail fast; regional endpoints; `gcp.resourceLocations` Org Policy; VPC-SC perimeter. **Agent Search serves no Cloud region at all** (`global`, `us` and `eu` only), so the retrieval corpus cannot be in-country at any setting: it defaults to `global`, which carries no residency guarantee. `us` or `eu` confines it to one jurisdiction and is the stronger choice where a residency obligation bites, and `gcp.resourceLocations` must be wide enough to permit whichever is chosen. | `config/settings.yaml` (`markets`), `config.market_profile`, `infra/terraform/variables.tf`, `org_policy.tf`, `vpc_sc.tf` |
| **P-04** | Minimise data to the model | Mkt1 sends public and aggregate market data only, no customer PII; the model-boundary callback still guardrail-screens every prompt and response, and spans capture no content | `agent/callbacks.py`, `domain/brief_service.py` |
| **P-05** | Grounding over fine-tuning | Briefs are grounded on the internal research corpus (Hrz2 File Search) plus deep research; no training on data | `ports/knowledge_base.py`, `ports/research.py`, `adapters/*/file_search_kb*`, `adapters/*/deep_research*` |
| **P-06** | Human-in-the-loop / maker-checker | Every `MarketBrief` and `CompetitorAnalysis` is `requires_human_review=True`; a qualified strategist disposes before anyone acts; the escalation is ROUTED to the Hrz7 maker-checker console (rule R8), not left as a boolean | `domain/brief_service.py`, `domain/models.py`, `ports/review_router.py`, `adapters/*/review_router.py` |
| **P-07** | Auditable and explainable by design | Every interaction writes a WORM `AuditEvent` with the decision and citations; the ADK after-agent callback audits again at the model boundary | `domain/brief_service.py`, `adapters/gcp/cloud_logging_audit.py`, `agent/callbacks.py` |
| **P-08** | Eval-gated promotion | Offline eval gate scores brief groundedness, citation accuracy, diff accuracy and review safety; Hrz4 at promotion | `eval/run_eval.py`, `ports/observability.py` (`EvaluationGatePort.gate`) |
| **P-09** | Defense in depth / zero trust | CMEK, least-privilege IAM, private endpoints, a distinct agent identity; the guardrail screens twice (domain pipeline and model-boundary callback) | `infra/terraform/kms.tf`, `iam.tf`, `agent/callbacks.py` |
| **P-10** | Provenance on every claim | Every brief statement and competitor delta carries a source-and-page `Citation`; the model only narrates retrieved or derived sources, never invents a figure | `domain/models.py` (`Citation`), `domain/brief_service.py` |
| **P-11** | Cost and latency control | A small triage-tier model handles routing / pre-checks; the reasoning model only narrates the already-computed result | `config.py` (`ModelSettings.triage`), `agent/grounding_agent.py` |
| **P-12** | Reversibility / documented exit | The `local` adapters run the whole pipeline off-cloud today (the working proof), and the `onprem` placeholders satisfy the same Protocols as the fail-fast sovereign target; the contract test proves parity for both | `adapters/local/*`, `adapters/onprem/*`, `tests/contract/test_port_parity.py`, `docs/onprem-migration.md` |
| **P-13** | Fair, consented marketing (advertising compliance) | Mkt1 produces internal strategy artifacts (briefs, competitor analysis), not customer-facing marketing, so it publishes no advertising itself; any output that becomes customer-facing must pass Mkt6 (rule R7). The agent instruction forbids drafting customer-facing ad copy here | `agent/root_agent.py` instruction, R7 below |

---

## Dependency rules

Mkt1's mandatory dependencies are **Hrz2, Hrz3, Hrz4 (gate) and Hrz5** (see `systems/`). Each
platform rule is satisfied by consuming the sibling service through a `platform` adapter (with
an on-prem stub), never by re-implementing the concern.

| Rule | Requirement | How Mkt1 satisfies it | Evidence |
|------|-------------|---------------------|----------|
| **R1** | Customer PII handling: Hrz1 guardrail + DLP redaction | **n/a for PII** (Mkt1 handles public + aggregate market data, no customer PII: C2/C3/C4 are n/a in the practices audit). The Hrz1 guardrail is still consumed for prompt-injection and unsafe-output screening at both the pipeline and the model boundary | `ports/safety.py`, `domain/brief_service.py`, `agent/callbacks.py` |
| **R2** | Audit to Hrz5 | Every interaction writes an immutable WORM `AuditEvent`; the `platform` adapter posts to Hrz5 `/v1/audit` | `adapters/gcp/cloud_logging_audit.py`, `adapters/platform/remote_audit.py` |
| **R3** | Governed RAG via Hrz2 | The internal research / brand corpus is retrieved via Hrz2 governed File Search | `ports/knowledge_base.py`, `adapters/platform/remote_knowledge_base.py` |
| **R4** | Register in Hrz3 | The A2A AgentCard is published at `/.well-known/agent-card.json` and resolvable via Hrz3; the governed MCP tool catalog scopes access least-privilege | `agent/agent_card.py`, `api/app.py`, `adapters/platform/remote_registry.py`, `adapters/gcp/mcp_tool_catalog.py` |
| **R5** | Hrz4 promotion gate | `EvaluationGatePort.gate` checks the Hrz4 thresholds before promotion; the offline gate guards merges | `ports/observability.py`, `adapters/platform/remote_evaluation.py`, `eval/run_eval.py` |
| **R6** | Validated by Rsk3 at intake | As a new project, Mkt1 is validated by the Rsk3 intake validator externally. n/a in-repo (Rsk3 is the validator, not a Mkt1 runtime dependency) | intake handled by Rsk3 externally |
| **R7** | Marketing compliance via Mkt6 | Mkt1 produces internal strategy artifacts, not customer-facing marketing. Any output that becomes customer-facing must pass Mkt6 (per-market advertising / consumer-protection claim check, brand guidelines, marketing consent) and screen via Hrz1. The agent forbids drafting customer-facing copy here | `agent/root_agent.py` instruction; Mkt6 governance |
| **R8** | Route `requires_human_review` to Hrz7 | Every escalated brief is submitted to the Hrz7 Human-Review & Maker-Checker Console through the shared `review-kit` client (redact-before-wire); `local` enqueues to a transactional outbox so the routing path runs offline, `gcp`/`platform` submit over S2S to Hrz7's service intake | `ports/review_router.py`, `adapters/{local,platform,onprem}/review_router.py`, `adapters/_review_payload.py` |

---

## Why Mkt1 has no customer-PII surface (R1, C2..C4)

- **Public and aggregate inputs only.** A brief is built from grounded public-web deep
  research plus an internal research / brand corpus. There is no per-customer record, no
  customer identifier, and no tenant-partitioned customer data (contrast Mkt5, the only
  per-customer marketing repo). The practices audit records C2/C3/C4 as **n/a by design**.
- **The guardrail still runs, twice.** Absence of PII is not absence of safety: the Hrz1
  guardrail screens INPUT and OUTPUT inside the domain pipeline and again at the ADK model
  boundary (`agent/callbacks.py`), so prompt injection and unsafe output are caught even
  though there is no PII to redact.
- **Maker-checker on a consequential output (P-06).** A brief and a competitor analysis are
  strategy inputs, so both always require human review before anyone acts on them.
- **WORM audit, page-level citations (P-07, P-10).** Every interaction is recorded immutably
  with the decision and the citation set, so a reviewer can trace each claim to its source.

---

## Appendix: regulator crosswalk (adopter-owned)

The `P-*` / `R*` catalog above is this build's internal control language. A regulated adopter
maps those controls onto its own supervisor's requirements. The rows below are a **reference
mapping** for the home markets (JP / AU / SG); a fork adds a column (or a sibling table) per
additional regulator. This appendix is *adopter-owned*: it is a template, not legal advice, and
your compliance function owns the mapping and any gaps.

| Mkt1 control | Reference regime | What a supervisor looks for |
|---|---|---|
| P-06 maker-checker; P-05 grounding | MAS FEAT (Accountability); general fair-dealing guidance | A qualified human disposes of every consequential strategy output; the AI is decision-support |
| P-07 WORM audit; P-10 provenance | MAS TRM (auditability); record-keeping obligations | Immutable, reproducible records; every claim traceable to its source |
| P-13 / R7 marketing compliance | SG ASAS / consumer-protection; AU ACCC / ASIC advertising; JP fair-trade advertising | Customer-facing outputs pass an advertising / consumer-protection claim check before publication |
| P-03 residency; P-12 exit | MAS Outsourcing / Cloud guidelines | In-country data residency and a demonstrable exit / portability plan |
| P-08 quality / model-risk gate | MAS FEAT; model-risk expectations | A promotion gate with groundedness / accuracy / safety metrics and model documentation |

**To add another regulator** (FCA, HKMA, RBI, ...): copy this table, replace the reference
column with that supervisor's instrument and section numbers, and re-review the third column
with local counsel. The Mkt1-control column is stable across regulators; only the mapping
changes. The sibling **Rsk1** `compliance-advisory` and its control-mapping module
(`domain/control_mapping/`) exist to generate and maintain these crosswalks at scale.
