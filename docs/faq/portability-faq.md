# Portability FAQ

For architecture, cloud-governance, and exit-planning teams. The claim this repo makes is "no
vendor lock-in, demonstrably", and it is designed to be *shown*, not asserted.
Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`docs/onprem-migration.md`](../onprem-migration.md), [`DEMO.md`](../../DEMO.md).

### What does "portable" actually mean here?

Two axes, each with a rehearsed exit: **compute** (the whole stack migrates by a one-line
profile change, no domain edits) and **data** (the audit trail exports in an open, documented
format and reloads elsewhere with integrity re-verified). Identity resolves across hosts by an
adapter swap rather than a rewrite.

### How does the profile switch work?

The pure-domain core speaks only to `typing.Protocol` **ports**; four **adapter families**
implement them, and `config/settings.yaml` binds one adapter per port per profile. Setting
`MKT_INTEL_PROFILE` (or `profile:` in the settings) rebinds the entire stack:

- `local`: a WORKING offline stack (SQLite FTS5 knowledge base, deterministic LLM,
  hash-chained audit). No Google Cloud SDK. The default for dev/test/CI.
- `gcp`: real managed services (Gemini, Agent/Discovery Engine search, Cloud Logging WORM,
  Cloud Trace, Gen AI Evals).
- `platform`: thin HTTP clients delegating to the sibling horizontal-platform and
  de-risking services.
- `onprem`: placeholder stubs that still satisfy every Protocol (the sovereign-exit target),
  failing fast with `NotImplementedError`.

No `domain/` code changes across any of these. The contract test
(`tests/contract/test_port_parity.py`) proves both `local` and `onprem` construct and satisfy
every port with no cloud SDK installed, and `test_behavioral_parity.py` proves the `local`
adapters are byte-for-byte deterministic while `onprem` and `platform` placeholders fail fast.

### Does the kernel/vertical split affect portability?

It reinforces it. The kernel machinery in `domain/models.py` (citations, LLM envelope,
guardrail verdict, audit, eval, AgentCard) is vertical-neutral and reusable across products;
the `MarketBrief` / `CompetitorAnalysis` artifacts are the `market-intelligence` vertical. Neither imports a
cloud SDK or a framework, so a fork for a different research vertical keeps the kernel and the
port layer, and the portability guarantees transfer for free.

### How do we get our data out?

The audit trail is a hash chain (via the shared `hex-service-kit` `HashChainedAuditLog`) that
exports to JSON Lines, one `{seq, prev_hash, entry_hash, event}` object per line, and reloads
into a fresh store with the chain re-verified line by line. Records rehydrate to first-class
`AuditEvent` objects (`domain/serialization.py`). Briefs and competitor analyses serialize the
same way via `to_jsonable`. The exit story for the audit trail is "copy the JSONL file", not
"migrate a product".

### Is on-prem / sovereign deployment real or aspirational?

The `onprem` adapters are deliberate fail-fast placeholders (they raise
`NotImplementedError`) that nonetheless satisfy every Protocol and construct with a single
`Settings` arg, so the *interface contract* for a sovereign migration is proven and enforced
by CI today. The actual on-prem implementations are the migration work, scoped in
[`docs/onprem-migration.md`](../onprem-migration.md). This repo is not the sovereign-exit
*planner* (that is the sibling `operational-resilience-mapping`, module
`domain/concentration_exit/`); this repo is one of the systems whose exit that planner
reasons about.

### Does residency compromise portability?

No: residency is a deploy-time pin (a single in-country region, default `asia-southeast1` /
Singapore, with an Org Policy resource-location allowlist, CMEK, and a VPC-SC perimeter), and
portability is the ability to change *where* the stack runs by configuration. They are
orthogonal. The region is validated to fail fast, and a second region is a tfvars change, not
a fork. Residency-violation CI gating overlaps with the sibling `architecture-validator` (`domain/residency/`), which a fork should run rather than
re-implement.

### What is a single script I can run to prove it?

A one-command executable portability check (profile swap, port parity, tamper-evident audit,
export/reload) is the tracked F3 gap. Today the proof is the contract suite:
`MKT_INTEL_PROFILE=local` and `MKT_INTEL_PROFILE=onprem` both construct every port under
`tests/contract/`, and the full offline gate (`make gate`) runs with no cloud SDK.
