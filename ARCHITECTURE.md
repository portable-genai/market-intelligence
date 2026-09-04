# ARCHITECTURE: `market-intelligence` Market Intelligence and Competitor Analysis

## Hexagonal ports and adapters

`market-intelligence` is built as a hexagon: a pure-stdlib **domain core** surrounded by typed **ports**, with
interchangeable **adapter families** selected by a single profile switch. The domain has
zero dependency on any framework, SDK or cloud. That is what makes it testable offline,
portable across vendors, and honest about its boundaries.

```
                +-------------------- driving (inbound) --------------------+
                |  cli/main.py        api/app.py         agent/ (A2A)       |
                +----------------------------+------------------------------+
                                             v
                          +------------------------------------+
                          |  domain/  (PURE, stdlib only)      |
                          |    models.py                       |
                          |    dedup_service.py    (engine 1)  |
                          |    diff_service.py     (engine 2)  |
                          |    trend_service.py    (engine 3)  |
                          |    swot_service.py     (engine 4)  |
                          |    brief_service.py    (orchestr.) |
                          +------------------+-----------------+
                                             v  ports (typing.Protocol)
   Research  Llm  KnowledgeBase  Guardrail  Audit  Tracer  Evaluation  Registry  ToolCatalog
                                             v
       +---------------+----------------+----------------+--------------------+
       | adapters/gcp  | adapters/local | adapters/platform | adapters/onprem |
       | (lazy SDK)    | (offline)      | (HTTP to `agent-guardrail-gateway`..`agent-observability`)  | (fail-fast stub) |
       +---------------+----------------+----------------+--------------------+
```

## The four profiles

| Profile | Role | Backing |
|---|---|---|
| `gcp` | primary, managed | Gemini Deep Research API, Grounding with Google Search, File Search, Model Armor, Cloud Logging WORM, Cloud Trace, Gen AI eval. SDK imports are lazy. |
| `local` | dev / test / CI default | a WORKING offline stack: a deterministic deep-research synthesizer over a seeded SQLite FTS5 corpus, a deterministic schema-driven LLM, a heuristic guardrail, append-only audit, no-op tracer, in-process registry / tool-catalog, the offline eval gate. SDK-free and seedable. |
| `platform` | shared-platform reuse | thin HTTP clients to the shared `agent-guardrail-gateway`, `enterprise-knowledge-base`, `agent-registry`, `model-quality-gate` eval, `agent-observability`. |
| `onprem` | portability proof | fail-fast `NotImplementedError` stubs satisfying the same Protocols. |

Switching the whole backend is a one-line `profile` change in `config/settings.yaml` (or
the `MKT_INTEL_PROFILE` env var). The contract test proves the local and onprem families
satisfy every port Protocol, so the profiles never drift.

## Why the engines are deterministic

The consequential outputs of a market-intelligence system (which competitor moves changed,
how strong a trend is, which options to play) drive real money and strategy. They must be
auditable: an analyst has to be able to re-run them and get the same answer, and a test has
to be able to pin them. So each lives in a pure, frozen domain service with no LLM, clock,
randomness or I/O inside, and tunables exposed as fields. The LLM's job is narrow:
narrate the already-computed result into prose. It never produces the number that matters.

See the `deterministic-domain-service` skill in `.agents/skills/`.

## Generic, multi-vertical, APAC by construction

* `Vertical` (banking, online retail) and `Market` (JP, AU, SG) are enums; the active values
  are settings.
* The engines take `market` and `vertical` as parameters and carry them through; they never
  branch on a specific market or vertical.
* Per-market residency region, locales and rule references come from `MARKET_PROFILES` plus
  the `markets:` overrides in `config/settings.yaml`. The local seed (`adapters/local/_seed.py`)
  is keyed by `(market, vertical)` and spans both verticals across all three markets.

Adding a market or vertical is a config + seed change, not a code change.

## Data residency

Each market's residency region is validated and selectable at deploy via
`Settings.market_profile().region` (JP `asia-northeast1`, AU `australia-southeast1`,
SG `asia-southeast1`). The GCP adapters construct their clients against the resolved region,
and the WORM audit bucket is regional. Web egress on the `gcp` profile is contained in the
Deep Research grounding sub-agent.

## Auditability

Every brief is written to the audit sink as an immutable record (`Decision.ESCALATED`,
maker-checker). Every claim, delta and SWOT item carries its `Citation`s, and the brief
serialises to plain JSON for an explainable, audit-first view (see the `audit-first-demo`
skill and `DEMO.md`).
