# DEMO: Mkt1 Market Intelligence and Competitor Analysis

Two ways to demo Mkt1: **Demo A**, a fully offline run on the `local` profile (no Google
Cloud, no credentials), and **Demo B**, the managed run on the `gcp` profile with the
residency region and the vertical selectable. Both use the same domain code and the same
obviously-fictional synthetic data, so the offline demo is a faithful preview of the managed
one.

## Demo A: fully offline (local profile, no Google Cloud)

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export MKT_INTEL_PROFILE=local
```

### A cited market brief (CLI)

```bash
mkt-intel brief "savings and account fees" --market SG --vertical banking
mkt-intel brief "loyalty programmes" --market JP --vertical online_retail
mkt-intel brief "home loan rates" --market AU --vertical banking
```

Each brief prints the summary, the scored trends, the deterministic competitor-move diff
(what is new, changed or withdrawn, with the exact attributes that moved), the ranked
where-to-play options, the source list, and the citations. The human-review banner is always
shown (maker-checker): the agent proposes, a qualified strategist disposes.

### A competitor analysis (CLI)

```bash
mkt-intel competitor-analysis "checkout payment options" --market AU --vertical online_retail
```

### The scripted demo plus the audit-first HTML renderer

```bash
make demo
# equivalently:
#   MKT_INTEL_PROFILE=local PYTHONPATH=src python scripts/demo.py
#   MKT_INTEL_PROFILE=local PYTHONPATH=src python scripts/render_brief_ui.py scripts/out
```

`scripts/demo.py` runs four (topic, market, vertical) scenarios spanning both verticals
across all three markets, prints a readable cited trace, and writes one audit-view JSON per
brief to `scripts/out/`. `scripts/render_brief_ui.py` turns those into dependency-free static
HTML pages (`scripts/out/index.html` plus one page per brief) that match the console palette,
so screenshots are trivial and never drift. Everything is deterministic and offline.

### The presenter-controlled live demo

```bash
make demo-server          # stdlib-only server on http://localhost:8110
```

Open the page and click **Next** to reveal one cited brief per step, walking banking and
online retail across JP, AU and SG. The presenter controls the pacing; nothing calls out to
the network.

### The presenter-paced browser walkthrough (Playwright)

A guided, narrated run of the same demo server: a real Chrome window opens, each step is
announced on the terminal (never on screen, so the audience sees a clean console) and waits
for you to press Enter before it clicks "Next" and highlights the panel to look at.

```bash
# one-time
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

# terminal 1
make demo-server

# terminal 2
.venv/bin/python scripts/demo_playwright.py
```

Unattended (self-test / recording): `HEADLESS=1 DEMO_AUTO=1 .venv/bin/python scripts/demo_playwright.py`.

### The HTTP API plus the thin console

```bash
make run-api              # uvicorn on :8100 (the real FastAPI app), PROFILE=local
curl localhost:8100/healthz
curl -s localhost:8100/v1/brief \
  -H 'content-type: application/json' \
  -H 'X-Dev-Persona: approver' \
  -d '{"topic": "savings and account fees", "market": "SG", "vertical": "banking"}'

# in a second terminal, the thin Next.js console, on a PRODUCTION build:
cd ui && npm install && npm run build && npm run start   # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE` needs no setting here: the console already defaults to `:8100`, the
port `make run-api` binds. Demo the BUILT console, never `make run-ui`. That target is the
developer loop and serves `next dev`, and the standing rule for every demo in the fleet is
`org-metadata/docs/demos/demo-inventory.md`: production builds only.

Identity is resolved server-side, never from the request body: there is no `actor` field.
In the `local` profile the optional `X-Dev-Persona` header picks a seeded persona (default
= the first one); the UI shows a "Demo identity" picker for the same purpose. In secure
mode the backend verifies the Cloud IAP assertion instead. See
[docs/embedding-and-identity.md](docs/embedding-and-identity.md) for embedding the console
into a client portal and the full identity contract.

The console has a config rail (topic, market with its residency region, vertical, optional
competitors) and renders the audit-first brief returned by the API: summary, cited claims,
trends, the competitor-move diff, the ranked where-to-play options, the sources, and the
human-review banner.

## The gate (what reviewers run)

```bash
make gate                 # ruff check + ruff format --check + mypy + pytest + eval
```

Everything runs on the `local` profile with the `[dev]` extra only (no `google-cloud-*`).
CI runs the same gate, boots the real API for a `/healthz` smoke, and builds the console.

## Demo B: managed (gcp profile, region + vertical selectable)

```bash
pip install -e ".[gcp,dev]"
export MKT_INTEL_PROFILE=gcp GOOGLE_CLOUD_PROJECT=your-project

# The residency region follows the market; the vertical is a flag. Pick either axis:
mkt-intel brief "savings and account fees" --market SG --vertical banking        # asia-southeast1
mkt-intel brief "multi-currency wallets"   --market JP --vertical banking        # asia-northeast1
mkt-intel brief "loyalty programmes"       --market AU --vertical online_retail  # australia-southeast1
```

The `gcp` adapters wrap the **Gemini Deep Research API** plus **Grounding with Google
Search** for market research and competitor analysis, the **Gemini File Search** tool for the
internal brand/research corpus, **Gemini** for narration, and the managed equivalents for
audit (**Cloud Logging** WORM), tracing (**Cloud Trace** via OpenTelemetry), the agent
registry (A2A AgentCard), the tool catalog (MCP) and the promotion gate (**Gen AI evaluation
service**). Every Google SDK import is lazy, so the local and on-prem profiles import the
package with no `google-*` installed.

The residency region is selectable per market and **validated** against the per-market
allow-list (JP `asia-northeast1`, AU `australia-southeast1`, SG `asia-southeast1`). A region
outside that set is rejected before any network call, so a managed run can never cross the
configured residency boundary. Region, locale and vertical are config plus seed, never
hard-coded.

### On-prem (sovereign migration target)

```bash
export MKT_INTEL_PROFILE=onprem
mkt-intel brief "savings and account fees" --market SG --vertical banking
# exits 2 with a clear migration message; the on-prem adapters are fail-fast placeholders
# that satisfy the same Protocols, proving interface parity (no lock-in).
```

## Notes on the data

All company names are invented and suffixed FICTIONAL, and every URL points at
`example.test`. Nothing in any demo touches real or production data.
