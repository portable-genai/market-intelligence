# market-intelligence

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

Catalog id `market-intelligence`. Cited market briefs and competitor analysis over grounded research and an
internal research corpus: source and claim dedup with provenance, competitor-move diff, trend
scoring and the SWOT synthesis are deterministic, and the model narrates the computed result.

## Concrete bindings

| | |
|---|---|
| Catalog id | `market-intelligence` |
| Package | `src/market_intelligence/` |
| Profile variable | `MKT_INTEL_PROFILE` |
| Adapter families | `gcp`, `local`, `onprem`, `platform` |
| Gate | `make gate` (`lint format typecheck test eval demo-selftest portability`) |

`config.resolve_profile` is the only reader of that variable, and it resolves three states.
Unset is NO CHOICE: the SDK-free adapters bind so the process can still boot, but every
relaxation sees `UNCONSENTED_PROFILE` (`unconfigured`) instead of `local`. Set-and-empty raises
`ConfiguredEmptyError` rather than inheriting the unset case. An unknown or mis-capitalised
value raises, because the comparison against `RUNTIME_PROFILES` is exact and case-sensitive.
`tests/unit/test_profile_single_source.py` fails the build if any other module re-derives the
profile from the environment, in Python or in the shipped settings file.

## What this repository still owes

The `Capability gaps` cell on this repository's row in the maintainer's system tracker
is the authoritative list. Its verdict against the shared checks, including the ones it
does not pass, is in [`docs/practices-audit.md`](docs/practices-audit.md).
