# Adoption FAQ

For an engineering lead forking this repo as their institution's base. The step-by-step is
[`docs/ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?" questions.

### How do I rebrand it for my institution?

`scripts/rename_fork.py` rewrites the package name, CLI entry point, `MKT_INTEL_` env prefix,
and resource ids in one pass (preview with `--dry-run`, apply with `--yes`). Then recreate
the venv, `pip install -e ".[dev]"`, and run `make gate`. The script does the mechanical
rename; the human decisions (region, IdP posture, market/locale overrides, engine tunables,
fixtures, eval golden set) are the checklist in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags** (semver). The repo declares a **core-vs-adopter-owned boundary** (ADOPTING section 2):
upstream owns the kernel machinery in `domain/models.py`, `ports/`, `tests/contract/`, the
eval harness mechanics and CI; you own `config/settings.yaml` values, fixtures, the seed
corpus, `adapters/onprem/*`, UI theming, and the eval golden set. Rebase your adopter-owned
changes onto each release rather than merging `main` continuously, and merge conflicts stay
in files you were told to expect.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list, and the contract test fails loudly if you miss part of it
(`test_port_protocols_matches_settings_adapters`): define the `@runtime_checkable` Protocol
under `ports/`, re-export it from `ports/__init__.py`, implement one adapter per profile (at
least `local` and `onprem`), bind all of them in `config/settings.yaml`, add the port to
`PORT_PROTOCOLS` in the parity test, add a `cached_property` on the `Container`, and wire it
in `api/deps.py`. Full instructions in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

### How do I add a new deterministic engine or output panel?

An engine is pure domain: add `domain/<name>_service.py` (stdlib only), re-export it from
`domain/services.py`, thread any owned constants through config rather than hard-coding them,
construct it in `api/deps.py`, and unit-test it. The dedup, diff, trend and SWOT services are
the worked examples. For an output panel, the renderer (`scripts/render_brief_ui.py`) renders
attached artifacts when present.

### How do I change the taxonomy (source kinds, competitor axes, market vocab)?

The vocabularies are `StrEnum`s (via the shared `hex-service-kit` commons) and the engines
are typed on `str`, so you extend the vocabulary without editing engine code. Serialized JSON
values are the enum strings. To replace the taxonomy wholesale for a different vertical, edit
the enums in `domain/models.py` and the label maps in the UI.

### How do I retune the engines without touching code?

The market residency knobs (region, locale, currency) are config-driven via the `markets:`
overrides and `MarketOverride`. The engine tunables (trend half-life, rising band, dedup
thresholds, SWOT/diff weights) currently live as frozen-dataclass defaults; owning them
through a settings `policy:` section is the tracked B4 adoption step. Until then, subclass or
construct the services with your values in `api/deps.py`.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate (check F2, PASS). The offline demo is code
(`make demo` runs `scripts/demo.py` over the real services), and the renderer and demo server
emit stable `data-*` evidence hooks for every load-bearing figure. `make demo-selftest`, which
`make gate` runs, builds all four live briefs in process and then starts the REAL demo server on
an ephemeral port, walks every presenter step over HTTP and compares each hook in the served
bytes against the value the running app just computed, so a refactor that breaks a step or
quietly stops recomputing a figure fails the gate rather than surfacing in front of an audience.
`make demo-browser` adds the last layer: headless Chromium loads the same served pages and reads
the figures out of the live DOM. Playwright is pinned in the `[demo]` extra rather than `[dev]`,
because the browser binary is a network download and the day-one offline install must not need
one; that stage skips itself when the extra is absent. Both stages have been proven able to go
RED against a planted stale figure and a stripped panel hook. If you diverge, keep the hooks:
they are the contract every stage reads.

### Does the CI run for my fork out of the box?

Yes. CI and the eval gate run on the `local` profile with **no cloud credentials and no org
secrets** (`MKT_INTEL_PROFILE: local`), so a fork's build is green immediately. You add
secrets only when you wire the `gcp` / `platform` profiles. Note the eval gate measures the
*reference* vertical until you rebuild the golden set; that is an explicit adoption step, not
a silent pass.
