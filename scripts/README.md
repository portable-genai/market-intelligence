# Demo scripts - Mkt1 Market Intelligence & Competitor Analysis

All scripts are SDK-free and run against the in-process `local` stack (no Google Cloud, no
API key, no live web grounding). They drive the real `MarketBriefService` over four
synthetic (topic, market, vertical) scenarios spanning both verticals across JP, AU and SG.
Run them from the repo root with the domain package on the path:

```bash
export PYTHONPATH=src
export MKT_INTEL_PROFILE=local
```

| Script | What it does |
|--------|--------------|
| `demo.py` | Runs the real brief service over four scenarios, prints a cited trace to stdout, and writes each audit view to `scripts/out/*.json`. Also the end-to-end smoke test for the slice. |
| `render_brief_ui.py` | Dependency-free static HTML renderer: reads the `demo.py` JSON output and writes the audit-first console pages (`scripts/out/index.html` + one page per brief), the same palette and markup as the live Next.js console. |
| `demo_server.py` | Live, presenter-controlled HTTP server (stdlib only) that reveals one of the four briefs per click, reusing `render_brief_ui.py` verbatim. `make demo-server`, then open `http://localhost:8110`. |
| `demo_playwright.py` | Headed, presenter-paced Playwright walkthrough of `demo_server.py`: narrates in the terminal only, clicks "Next" on your cue, and spotlights the panel to look at. See [`../DEMO.md`](../DEMO.md) for the two-terminal run. |
| `demo_selftest.py` | Drives every presenter step through the real in-process session, verifies rendered evidence, advance and reset behaviour, and runs in `make gate`. |
| `portability_demo.py` | Proves the bounded local profile and portable audit contract without requiring Google Cloud. |
| `lock.py` | Compiles both lockfiles and puts the header back, because `uv pip compile` REPLACES the output file: it writes its own two-line provenance comment and destroys the `tag = commit` map the pin tests check against. `make lock` runs this rather than uv directly. |

Every scenario is obviously-fictional synthetic data (see `demo.py` for the fixed set), so
screenshots and the walkthrough narration never drift between runs.
