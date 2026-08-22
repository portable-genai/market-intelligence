# Security FAQ

For an application-security team reviewing this repo before adopting it as a base.
Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md), [`COMPLIANCE.md`](../../COMPLIANCE.md),
[`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### How is a request authenticated? Can a client spoof its identity?

No. Identity is resolved **server-side** from the transport context by an `IdentityPort`
adapter (`api/security.py::get_principal` to `domain/identity.py`), never from the request
body. The request schemas carry no `actor` field (`api/schemas.py`), and any client-asserted
actor or ACL is discarded. The audit actor comes from the verified `Principal`. Per profile:
`local` = seeded dev personas resolved from the `X-Dev-Persona` header (no IdP, offline
only), secure profiles = the Cloud IAP injected assertion. There is no in-repo login flow to
harden.

### How is multi-tenant object-level authorization enforced?

By design there are **no per-customer objects to isolate**. The knowledge base is a single
shared internal research and brand corpus; `KnowledgeBasePort.search(RetrievalQuery)` carries
no principals and the port declares no ACL contract. This vertical builds market and
competitor research from public plus aggregate data and holds no per-tenant records, so
object-level authorization is absent by design (audit check C2 is N-A and justified in
[`docs/practices-audit.md`](../practices-audit.md)). Identity is still verified server-side.

### Is there any customer PII in the pipeline?

No. Inputs are market topics and competitor names; outputs are briefs synthesised from
public-web and aggregate research plus the internal brand corpus. No customer PII enters the
pipeline, so there is no PII de-identification boundary (checks C3/C4 are N-A). The runtime
guardrail (input and output screening around the LLM, `brief_service._guard`) is the sibling
**Hrz1** gateway, which this repo consumes rather than re-implements.

### What about the service-to-service calls in the `platform` profile?

Most `platform` adapters are unbuilt `NotImplementedError` phase stubs today (tracked by the
catalog S2S-auth plan). The one real outbound call, the Hrz4 eval client
(`remote_evaluation.py`), is re-based on the shared `agent-eval-kit` / `hex-service-kit`
clients: it attaches the shared S2S bearer credential and enforces an https-only base-URL
guard (the client refuses plaintext non-loopback), and gate mode refuses to run outside
`MKT_INTEL_PROFILE=platform|gcp`.

### Is the demo/dev server safe? Does anything bind 0.0.0.0 by default?

Under the `local` profile `main()` binds via `hex_service_kit.resolve_bind_host`, which
returns loopback (127.0.0.1) for the no-auth local profile unless
`MKT_INTEL_ALLOW_INSECURE_DEMO=1` is set; the Makefile defaults `API_HOST ?= 127.0.0.1`.
Secure profiles keep the container-friendly `0.0.0.0` (ingress fronted by the platform).
Proven by `tests/unit/test_netdefaults.py`.

### What HTTP security headers are set?

The API and the console are two separate surfaces and both are covered.

`api/app.py` middleware emits CSP `frame-ancestors` plus `X-Frame-Options` on API responses.
The console serves the full default-deny baseline: `default-src 'self'`, `base-uri 'self'`,
`form-action 'self'`, `object-src 'none'`, a per-request nonce plus `'strict-dynamic'` on
`script-src`, a `connect-src` scoped to `'self'` and the API origin, and the same
`frame-ancestors` allowlist, plus `X-Content-Type-Options: nosniff` and
`Referrer-Policy: no-referrer`. It is built once in `ui/lib/csp.mjs` and emitted from one
place, `ui/proxy.ts`; `npm run assert-hydratable` starts the built server and proves every
served script tag carries the served nonce. See
[embedding-and-identity.md](../embedding-and-identity.md) section 4e. HSTS on secure profiles
is terminated at the platform ingress and remains the open half of C6.

### CORS: can any origin call the API?

No. CORS is an explicit allowlist (`cors_allowlist`, from `MKT_INTEL_CORS_ORIGINS`), never
`*`. The localhost dev-origin fallback and the `X-Dev-Persona` header are **local-profile
only**, so a secure deploy that forgets `MKT_INTEL_CORS_ORIGINS` trusts nothing cross-origin.

### How tamper-evident is the audit trail? What are its limits?

The `local` audit store wraps the shared `hex_service_kit.audit.HashChainedAuditLog`: a
SHA-256 chain over canonical JSON with SQLite `UPDATE`/`DELETE` triggers enforcing
append-only, `verify_chain()` exposed, JSONL export/restore, and an honest-limits docstring.
Proven by `tests/unit/test_audit_chain.py`. In production the `gcp` profile uses a locked WORM
bucket. This repo does not *replace* the platform audit system (Hrz5); see
[features-faq.md](features-faq.md).

### Supply chain: are dependencies pinned and scanned?

Yes. Committed lockfiles (`requirements-dev.lock`, `requirements-gcp.lock`) are installed in
CI and the Docker build; the base image is pinned by digest; GitHub Actions are SHA-pinned;
`.github/dependabot.yml` proposes bumps; and a CI job runs `pip-audit` (on the lockfiles) plus
`npm audit` (on the UI). The shared commons packages are pinned by tag with an exact SHA in
both locks. `ruff` is pinned exactly.

### Where are secrets? Are any committed?

No secret values are in the repo. `config/settings.yaml` names only the env vars holding
secrets (the `*_env` variables); values are read at construction time and never logged. The
seed brand corpus and every fixture are obviously-fictional (names suffixed FICTIONAL, URLs at
`example.test`).

### What is explicitly out of scope / a residual risk?

- Most `platform` S2S delegates are unbuilt placeholders; only the Hrz4 eval client is real.
- The security-header baseline is being extended (C6). The demo anti-rot self-test (F2) and the
  one-command portability script (F3) are no longer gaps: both are PASS and both run inside
  `make gate`.
- This is a reference build: run your own pen-test, threat model, and model-risk review before
  any live-data deployment (stated throughout the docs).
