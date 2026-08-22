# Mkt1 Market Intelligence and Competitor Analysis (`market-intelligence`)

**Industries:** Retail & e-commerce, Banking, Telecom, Consumer goods, Travel & hospitality, Media

Cited market briefs and competitor analysis from grounded deep research and an internal
research corpus, built ports-and-adapters on the Gemini Enterprise Agent Platform.

This is **generic marketing intelligence**, not a bank-specific tool. It supports BOTH
**banking** and **online retail** as first-class, configurable verticals, and the **Japan,
Australia and Singapore** markets as first-class config and seed (residency regions, locales
and per-market rules), never hard-coded.

The deterministic engines are the heart of the system: source/claim dedup with provenance,
competitor-move diff, trend scoring, and SWOT / where-to-play synthesis. The LLM only
narrates and drafts over the already-computed result. Every claim that leaves the system
carries a citation, and every consequential output requires human review (maker-checker).

## What it produces

* A **MarketBrief**: a cited summary, the key deduplicated claims, scored trends, the
  competitor analysis, and the full source list, for one `(topic, market, vertical)`.
* A **CompetitorAnalysis**: the deterministic competitor-move diff (what is new, changed or
  withdrawn since the last snapshot) plus a SWOT and a ranked set of where-to-play options.

Both always set `requires_human_review=True`.

## Generic, multi-vertical, APAC

| Axis | Values | Where it lives |
|---|---|---|
| Vertical | `banking`, `online_retail` | `vertical` setting + per-vertical seed |
| Market | `JP`, `AU`, `SG` | `market` setting + `markets:` profiles in settings.yaml |
| Residency region | `asia-northeast1` (JP), `australia-southeast1` (AU), `asia-southeast1` (SG) | per-market profile, validated by `config.market_profile()` |
| Locale | `ja` + `en` (JP), `en` (AU, SG) | per-market profile |

Adding a market or vertical is a config + seed change, not a code change. No bank-only logic
is baked into the domain; banking is one vertical and online retail is another.

## Architecture in one paragraph

A pure-stdlib domain core (`domain/`) reaches every external service through a typed
`Protocol` port (`ports/`). Each port has interchangeable adapter families selected by one
profile switch:

| Profile | Role | Backed by |
|---|---|---|
| `gcp` | primary | Gemini Deep Research API, Grounding with Google Search, File Search, Model Armor, Cloud Logging WORM, Cloud Trace, Gen AI eval (lazy SDK imports) |
| `local` | dev / test / CI default | a WORKING offline stack: SQLite FTS5 corpus, a deterministic deep-research synthesizer, a deterministic LLM, all SDK-free and seedable |
| `platform` | shared-platform reuse | thin HTTP clients to the shared Hrz1/Hrz2/Hrz3/Hrz4/Hrz5 services |
| `onprem` | portability proof | fail-fast `NotImplementedError` stubs satisfying the same Protocols |

Switching the whole backend is a one-line `profile` change, never a code edit.

## Quick start (offline, no Google Cloud)

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # no google-cloud-* needed for the local profile

export MKT_INTEL_PROFILE=local
mkt-intel brief "savings and account fees" --market SG --vertical banking
mkt-intel brief "loyalty programmes" --market JP --vertical online_retail
mkt-intel competitor-analysis "home loan rates" --market AU --vertical banking
```

Every line of the brief is grounded in the bundled, obviously-fictional synthetic corpus
(company names suffixed FICTIONAL, all URLs at `example.test`).

## The gate (green before any change lands)

Run in a fresh `[dev]`-only venv (no `google-cloud-*`):

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest -m "not integration" -q
python eval/run_eval.py            # exit 0 iff every metric clears its threshold
```

## Ports

| Port | Concern | GCP adapter | Local adapter |
|---|---|---|---|
| `ResearchPort` | deep research / web grounding + competitor snapshots | Gemini Deep Research + Google Search | deterministic synthesizer over the seeded corpus |
| `LlmPort` | narration / drafting (never the numbers) | Gemini | deterministic schema-driven narrator |
| `KnowledgeBasePort` | internal research / brand corpus | File Search / Agent Search | SQLite FTS5 index |
| `GuardrailPort` | input/output safety | Model Armor | heuristic |
| `AuditSinkPort` | immutable WORM audit | Cloud Logging | append-only SQLite |
| `ObservabilityTracerPort` | tracing / FinOps | Cloud Trace (OTel) | no-op |
| `EvaluationGatePort` | model-risk gate | Gen AI evaluation service | in-repo offline gate |
| `AgentRegistryPort` | A2A AgentCard registry | A2A registry | in-process |
| `ToolCatalogPort` | governed MCP tools | MCP catalog | in-process |

## The deterministic engines (`domain/`)

| Engine | File | What it decides |
|---|---|---|
| Claim/source dedup + provenance | `dedup_service.py` | collapses near-duplicate claims (token-overlap), merges citations, de-dups sources by URL |
| Competitor-move diff | `diff_service.py` | NEW / CHANGED / WITHDRAWN moves, the exact changed attributes, severity-ranked |
| Trend scoring | `trend_service.py` | recency-weighted 0..1 momentum + RISING/STEADY/FADING |
| SWOT / where-to-play synthesis | `swot_service.py` | threats from the diff, opportunities from trends, ranked options by attractiveness x right-to-win |

Each is a frozen, pure dataclass: same inputs (including an `as_of` date passed in) produce
the same output, with no LLM, clock, randomness or I/O inside. See `SPEC.md` and `docs/`.

## Layout

```
src/market_intelligence/
  domain/      pure stdlib: models + the four deterministic engines + the orchestrator
  ports/       typing.Protocol, @runtime_checkable
  adapters/    gcp/ (lazy SDK) · local/ (offline) · platform/ (shared services) · onprem/ (stubs)
  config.py    Settings + Container (DI)
  api/  cli/   thin driving adapters (FastAPI on :8100, the `mkt-intel` CLI)
config/settings.yaml   profile -> {port: adapter} bindings + per-market profiles
eval/run_eval.py       offline quality gate over the synthetic golden set
scripts/               offline demo, audit-first HTML renderer, presenter server (outside the gate)
ui/                    thin Next.js console over the API (NEXT_PUBLIC_API_BASE)
tests/{unit,contract,integration}/
```

See `ARCHITECTURE.md`, `SPEC.md`, `CONTRIBUTING.md` and `DEMO.md`.
