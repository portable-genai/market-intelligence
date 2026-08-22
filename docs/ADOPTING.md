# Adopting this repo as your base

This repository is a **common base** that institutions fork to build their own grounded
market-intelligence and competitor-analysis agents. It ships a reusable hexagonal core (a
pure-stdlib domain, typed ports, swappable adapter profiles, a green offline gate) plus a
fully worked market-brief and competitor-analysis vertical (banking and online retail across
the JP/AU/SG markets) that you can keep, replace, or learn from.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical
rebrand** (one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (ports and profiles),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an engine, market, or vertical), the
> [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is split so the boundary is explicit:

| Layer | Where | For a new vertical |
|---|---|---|
| **Kernel** (vertical-neutral) | the stable `domain/kernel.py` import surface, `domain/serialization.py`, the engine mechanics in `dedup_service.py` / `diff_service.py` / `trend_service.py` / `swot_service.py`, and the generic ports | keep untouched |
| **Policy** (your numbers) | the market residency knobs and validated `policy:` block in `config/settings.yaml` (trend, dedup and SWOT values) | change by config, not code |
| **Vertical** (brief / competitor artifacts) | the `MarketBrief` / `CompetitorAnalysis` artifacts in `domain/models.py`, `brief_service.py`, the narration prompts, the local fixtures, the eval golden set, the UI brief views | rewrite for your artifacts |

If your product is another *grounded-research* vertical, most of the kernel and the
deterministic dedup / diff / trend / SWOT engines transfer directly; you replace the
artifact models and the prompts, and retune the market knobs and taxonomy.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): the stable `domain/kernel.py` surface,
  `ports/`, `tests/contract/`, the eval harness (`eval/run_eval.py` mechanics), CI
  workflows, and the hexagon wiring (`config.py` `Container`).
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the local
  fixtures and seed corpus (`adapters/local/_seed.py`), `adapters/onprem/*`, UI
  theming/branding, the golden eval dataset (`eval/datasets/`), and the `COMPLIANCE.md`
  jurisdiction rows.

Track upstream via git tags; rebase your adopter-owned
changes onto each release rather than merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name, CLI entry point, `MKT_INTEL_` env
prefix, and resource ids across the tree in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_market_intel --cli acme-intel \
    --env-prefix ACME --resource acme-market-intel --dry-run

# Apply:
python scripts/rename_fork.py --package acme_market_intel --cli acme-intel \
    --env-prefix ACME --resource acme-market-intel --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make gate
```

Add `--include-docs` to sweep Markdown prose too. The script deliberately does NOT touch
the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** Set `MKT_INTEL_REGION` (now `<PREFIX>_REGION`) and the Terraform
   `region`/`tfvars` to your in-country region. The build defaults to `asia-southeast1`
   (Singapore) with a fail-fast validation. See [`docs/runbook.md`](runbook.md).
2. **Identity / IdP.** The repo owns no login flow: secure profiles consume a Cloud IAP
   injected assertion, `local` uses seeded personas, `onprem` is a placeholder. Wire your
   IdP / IAP posture per profile. See
   [`docs/embedding-and-identity.md`](embedding-and-identity.md).
3. **Markets and locales.** Own the `markets:` overrides in `config/settings.yaml` and the
   `MARKET_PROFILES` domain constant so residency region, locale and currency match your
   deployment (JP/AU/SG are the reference set). This axis is residency/locale, not a
   national-identifier PII pack: this vertical holds no customer PII (see
   [`docs/faq/compliance-faq.md`](faq/compliance-faq.md)).
4. **Engine tunables.** Own the numbers your analysts care about: trend half-life and rising
   band (`trend_service.py`), dedup thresholds (`dedup_service.py`), the SWOT and diff
   weights. The defaults are a reference, not your policy.
5. **Reference data is fictional.** The seed brand corpus (`adapters/local/_seed.py`) and
   every fixture use obviously-fake names (company names suffixed FICTIONAL, URLs at
   `example.test`). Replace them with your own synthetic data. **Do not run against a live
   internal corpus without your own legal, security and model-risk sign-off.**
6. **Eval golden set.** Rebuild `eval/datasets/golden_briefs.jsonl` and the rubrics for your
   vertical: a fork inherits a green gate that measures the WRONG thing until you do. The
   gate structure is generic; the golden cases are yours.
7. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root),
   `infra/terraform/` (Org Policy, CMEK, VPC-SC, WORM), and the loopback-by-default binding
   before you expose anything.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it
*touches* are owned by sibling platform services, and you should integrate rather than
rebuild them (see [`docs/faq/features-faq.md`](faq/features-faq.md) for the full map): the
guardrail gateway (Hrz1), the governed knowledge base (Hrz2), the agent registry (Hrz3), the
AI-quality / eval gate (Hrz4), observability plus WORM audit (Hrz5), the compliance
assistant (Rsk1), and the Hrz7 human-review console (R8 routing). The `platform` profile's
adapters are thin HTTP clients to those services.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set region + Terraform tfvars to your in-country region.
- [ ] Confirmed the identity posture per profile (IAP / seeded personas / onprem).
- [ ] Owned the `markets:` overrides and locale/currency for your deployment.
- [ ] Owned the engine tunables with your analytics function.
- [ ] Replaced the seed brand corpus and every synthetic fixture.
- [ ] Rebuilt the eval golden set + rubrics for your vertical.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address).
- [ ] Decided which sibling platform services you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
