# SPEC: Mkt1 Market Intelligence and Competitor Analysis

## 1. Purpose and scope

Mkt1 turns external deep research and an internal research corpus into a cited **MarketBrief**
and **CompetitorAnalysis** for a `(topic, market, vertical)`. It is generic marketing
intelligence: banking and online retail are configurable verticals, and Japan, Australia and
Singapore are first-class markets. The Insights / Strategy function is the owner; the output
is decision support, never an auto-executed action.

## 2. Configuration axes

| Setting | Env | Values | Notes |
|---|---|---|---|
| `profile` | `MKT_INTEL_PROFILE` | `gcp` `local` `platform` `onprem` | selects the adapter stack; no default, an unset value grants no relaxation and refuses end-user identity |
| `vertical` | `MKT_VERTICAL` | `banking` `online_retail` | the active vertical |
| `market` | `MKT_MARKET` | `JP` `AU` `SG` | the active market |
| `grounding_enabled` | `MKT_GROUNDING_ENABLED` | bool | public-web grounding switch |

Per-market residency regions and locales come from `MARKET_PROFILES` (overridable under
`markets:` in `config/settings.yaml`), validated by `Settings.market_profile()`:

| Market | Region | Locales | Currency |
|---|---|---|---|
| JP | `asia-northeast1` (Tokyo) | ja, en | JPY |
| AU | `australia-southeast1` (Sydney) | en | AUD |
| SG | `asia-southeast1` (Singapore) | en | SGD |

Per-market and per-vertical advertising / consumer-protection rule sets (JP Act on
Specified Commercial Transactions and Premiums & Representations Act; AU Australian Consumer
Law / ASIC; SG PDPA and advertising standards; banking financial-promotion rules as one set
among others) are config + seed, surfaced by Mkt6 and consumed here as rule references; Mkt1
never hard-codes them.

## 3. Ports (the hexagon boundary)

| Port | Method(s) | GCP backing |
|---|---|---|
| `ResearchPort` | `research`, `competitor_snapshots` | Gemini Deep Research API + Grounding with Google Search |
| `LlmPort` | `generate`, `classify` | Gemini (`gemini-3.5-flash`, `gemini-3.5-flash`) |
| `KnowledgeBasePort` | `search` | File Search / Agent Search over the internal corpus |
| `GuardrailPort` | `screen` | Model Armor |
| `AuditSinkPort` | `record` | Cloud Logging locked WORM bucket |
| `ObservabilityTracerPort` | `span`, `record_token_usage` | Cloud Trace via OpenTelemetry |
| `EvaluationGatePort` | `evaluate`, `gate` | Gen AI evaluation service (Hrz4) |
| `AgentRegistryPort` | `register`, `get`, `list` | A2A AgentCard registry (Hrz3) |
| `ToolCatalogPort` | `list_tools`, `get_tool` | governed MCP tool catalog |

Every port is a `@runtime_checkable` `Protocol`; adapters need only structural conformance.

## 4. Deterministic engines (`domain/`)

Each is pure (stdlib only), replayable (same inputs, including an `as_of` date, produce the
same output) and unit-tested. The LLM never decides these.

1. **`ClaimDedupService`**: collapses near-duplicate claims (subject + Jaccard token
   overlap above a tunable threshold), merging citations from every corroborating source;
   de-dups sources by normalised URL keeping the highest score.
2. **`CompetitorDiffService`**: matches moves by a stable id (competitor + kind + summary
   slug), classifies each as NEW / CHANGED / WITHDRAWN / UNCHANGED, records the exact
   changed attributes (before/after), assigns severity by transparent rules, and orders
   deltas deterministically.
3. **`TrendScoringService`**: recency-weighted (half-life decay) 0..1 momentum per topic
   with a RISING / STEADY / FADING direction from the recent-vs-total ratio.
4. **`SwotSynthesisService`**: derives threats from the material diff, opportunities from
   rising trends, strengths/weaknesses from keyword-tagged claims, and ranks where-to-play
   options by `attractiveness x right-to-win` (weights are tunable fields).

## 5. Orchestration (`MarketBriefService`)

```
guardrail.screen(INPUT)          -> blocked: audit BLOCKED + raise GuardrailBlockedError
research.research                -> sources + claims
knowledge_base.search            -> internal-corpus passages (best-effort grounding)
dedup sources + claims           -> empty: raise ResearchEmptyError
research.competitor_snapshots    -> (previous, current)
diff.diff                        -> CompetitorDiff
trend.score_all                  -> trends
swot.synthesize                  -> SWOT + where-to-play
llm.generate                     -> summary narrative (narration only)
assemble MarketBrief             -> requires_human_review=True
guardrail.screen(OUTPUT)         -> blocked: audit BLOCKED + raise
audit.record                     -> Decision.ESCALATED (maker-checker)
```

## 6. Output artifacts

* **`MarketBrief`**: `summary`, `key_claims` (deduplicated + cited), `trends`,
  `competitor_analysis`, `sources`, `citations`, `requires_human_review`.
* **`CompetitorAnalysis`**: `diff` (severity-ranked deltas), `swot` (items + ranked
  options), `narrative`, `citations`, `requires_human_review`.

All artifacts serialise to plain JSON via `domain.serialization.to_jsonable` (enums to
values, datetimes to ISO, dataclasses to dicts).

## 7. Quality gate (Hrz4)

`eval/run_eval.py` runs the real `MarketBriefService` over a synthetic golden set on the
local profile and enforces: `brief_groundedness >= 0.80`, `citation_accuracy >= 0.90`,
`diff_accuracy >= 0.80`, `review_safety >= 0.99`. Exit non-zero on failure.

On the `platform` profile the same `EvaluationGatePort` is a real HTTP client
(`adapters/platform/remote_evaluation.py`) to Hrz4's hardened contract: `evaluate` posts to
`POST /v1/evaluations`, `gate` to `POST /v1/gate`, each with a structured `target` (`model`,
`prompt_version`, `dataset_id`, `system`) plus a top-level `dataset_id` and
`bundle: mkt1-market-intel`. Metrics are selected server-side by that registered bundle name
(never a bare metric list, which Hrz4 422s on), and the top-level `dataset_id` must equal
`target.dataset_id`.
