# Compliance FAQ

For compliance and model-risk teams assessing the repo's regulatory posture.
Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md) (the full principle-to-control map and
the JP/AU/SG regulator crosswalk appendix), [`SPEC.md`](../../SPEC.md).

### Is this making decisions autonomously?

No. It is a **decision-support** agent: every consequential output requires human review
(maker-checker). The deterministic engines produce a documented, replayable market brief and
competitor analysis; a qualified human disposes. When review is required the output sets
`requires_human_review=True`, the audit decision is `ESCALATED`, and the case is routed to the
sibling **Hrz7** human-review console (rule R8), never to auto-execution.

### How is customer PII handled?

There is none. This vertical builds market and competitor research from public-web plus
aggregate data and an internal brand corpus; it holds no per-customer records and no customer
PII. The PII de-identification and jurisdiction-pack checks (C3, C4) are therefore N-A by
design and justified in [`docs/practices-audit.md`](../practices-audit.md). The jurisdiction
axis here is JP/AU/SG **residency region and locale**, not national-identifier packs. Runtime
guardrail screening around the LLM is the sibling **Hrz1** gateway, consumed rather than
re-implemented.

### How is the work auditable / reproducible?

Every brief and competitor analysis writes an immutable WORM `AuditEvent` with the decision
and the citation set. Every claim carries a source `Citation`. The consequential work (dedup,
diff, trend scoring, SWOT) is deterministic, so an auditor can recompute any ranking or
finding from the same inputs. The enterprise WORM audit system is **Hrz5**; the in-repo
hash-chained store is the offline/local stand-in (see [security-faq.md](security-faq.md) for
its exact tamper-evidence limits).

### What is the model-risk story?

An offline eval gate (`eval/run_eval.py`, `--mode smoke|gate`) scores the reference vertical
against a golden set (`eval/datasets/golden_briefs.jsonl`) and fails the build below
threshold. The strictest metric is `review_safety >= 0.99`, which reads the hard-coded
`requires_human_review` flag and cannot go false-green. The enterprise promotion gate and
model documentation are the sibling **Hrz4** system; this repo's gate mirrors its thresholds
(registered bundle `mkt1-market-intel`) so merges are guarded locally, and `gate` mode refuses
to run outside `MKT_INTEL_PROFILE=platform|gcp`. A fork must rebuild the golden set for its
own vertical, or the gate measures the wrong thing.

### Which regulators does this map to?

`COMPLIANCE.md` maps the internal P-01..P-13 and R1..R8 controls to concrete code, plus an
**adopter-owned regulator crosswalk appendix** covering the JP/AU/SG markets. To add another
jurisdiction, copy the appendix table, swap the regulator-reference column, and re-review with
local counsel; the Mkt1-control column is stable across regulators. At scale, the sibling
**Rsk1** `compliance-advisory` and its control-mapping module (`domain/control_mapping/`)
generate and maintain these crosswalks; a large estate should integrate them rather than
hand-maintain the table.

### Is data residency enforced?

Yes at deploy time, with one stated exception: a single in-country region (default
`asia-southeast1` / Singapore), validated to fail fast, with a `gcp.resourceLocations` Org
Policy allowlist, CMEK, a VPC-SC perimeter, and a WORM log bucket.

**Agent Search is the one service that follows none of it:** it serves only `global` / `us` /
`eu`, so the retrieval corpus defaults to `global` and is unlocated. `us` or `eu` confines it to
one jurisdiction where an obligation bites, and the location Org Policy must be wide enough to
permit the choice. It is recorded in [`COMPLIANCE.md`](../../COMPLIANCE.md) rather than
absorbed.

The residency-violation CI gate is the sibling **Rsk3**
`architecture-validator` (`domain/residency/`); the exit/concentration-risk plan is **Rgc9**
`operational-resilience-mapping` (`domain/concentration_exit/`). This repo enforces residency
in its own infra and is one of the systems those tools reason about.

### Can we run it against a live internal corpus today?

Not without your own legal, security, and model-risk sign-off. The seed brand corpus and every
fixture are obviously-fictional (company names suffixed FICTIONAL, URLs at `example.test`), and
the docs state throughout that this is a reference build. The adoption checklist
(`docs/ADOPTING.md` section 6) lists the steps, replace reference data, own the market knobs
and engine tunables, confirm your identity posture, rebuild the eval golden set, that must
precede any live-data use.
