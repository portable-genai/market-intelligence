# Embedding and identity: client integration guide (`market-intelligence` market-intelligence)

How to run the `market-intelligence` Market Intelligence and Competitor Analysis agent standalone or
embedded inside an existing client web application, and how its server-verified identity
works. Everything described here is implemented in this repository; the "Further layers"
section at the end points at the reference repo for the designed extensions that are
deliberately out of scope here.

The agent ships as two cooperating pieces:

- **Backend**: a FastAPI service (default port `8100`) exposing the brief endpoints
  (`POST /v1/brief`, `POST /v1/competitor-analysis`), health (`GET /healthz`), and the
  local persona list (`GET /v1/personas`).
- **UI**: a thin Next.js console (default port `3000`) that calls the backend and renders
  the cited brief. `NEXT_PUBLIC_EMBED=1` drops the console's own chrome
  (`ui/app/layout.tsx`, `ui/app/page.tsx`); the mount sub-path, API base and the CSP
  frame-ancestors policy are build-time env vars (`ui/next.config.mjs`, `ui/lib/api.ts`).

## 1. The three deployment shapes

| # | Shape | Use when the host... | Identity |
|---|-------|----------------------|----------|
| 1 | **Embedded, same-origin reverse proxy** | has an existing portal and controls its edge (nginx or Next.js rewrites). The agent is served under the parent origin (for example `portal.client.com/market-intel/`) and iframed first-party: no CORS, no third-party cookies. | Cloud IAP verifies the user at the edge; the proxy forwards `x-goog-iap-jwt-assertion`; the backend re-verifies it (`adapters/gcp/iap_identity.py`). |
| 2 | **Standalone behind Cloud IAP** | has no host app, or wants a separate console at its own URL (DNS + HTTPS LB + IAP). | Same IAP-verified assertion; IAP plus Workforce Identity Federation gives SSO against the client IdP. |
| 3 | **Local dev, no auth** | is evaluating offline: no IdP, no GCP, no network. | Seeded dev personas selected via the `X-Dev-Persona` header (`adapters/local/identity.py`). |

## 2. Run locally, no auth

```bash
make install            # python venv, [dev] extra only (no google-cloud-*)
make run-api            # FastAPI on :8100 (the Makefile exports MKT_INTEL_PROFILE=local)
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8100 npm run dev
# open http://localhost:3000
```

The local profile binds `LocalPersonaIdentityAdapter`: four seeded personas, no IdP, no
AD/LDAP. The UI shows a "Demo identity" picker only when `GET /healthz` reports
`profile: local`; it lists `GET /v1/personas` and sends the chosen id as `X-Dev-Persona`.
With no header the first persona is the default; an unknown id is a 401.

| id | subject | tenant | entitlement principals |
|----|---------|--------|-------------------------|
| `analyst` | `demo.analyst@brand.example` | `demo-brand` | `group:mi-analyst`, `group:marketing` |
| `approver` | `demo.approver@brand.example` | `demo-brand` | `group:mi-analyst`, `group:marketing`, `group:mi-approver` |
| `auditor` | `demo.auditor@brand.example` | `demo-brand` | `group:audit` |
| `other-tenant` | `user@other-tenant.example` | `other-brand` | `group:mi-analyst` |

The `other-tenant` persona exists so per-tenant behaviour can be demoed offline. Curl
example (note: no `actor` anywhere in the body):

```bash
curl -s http://localhost:8100/v1/brief \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-Persona: approver' \
  -d '{"topic": "savings and account fees", "market": "SG",
       "vertical": "banking", "competitors": []}'
```

The audit record for that brief carries `actor: demo.approver@brand.example`, resolved
server-side, never taken from the request body.

## 3. Secure deployment on GCP (Cloud IAP)

In the `gcp` (and `platform`) profile the identity port binds `IapIdentityAdapter`:
authentication is configured ON the GCP service, not hand-rolled in the app.

1. Deploy the API (Cloud Run) behind an HTTPS load balancer with **Identity-Aware Proxy**
   enabled. IAP authenticates every request against the configured IdP and injects a
   signed JWT in `x-goog-iap-jwt-assertion`.
2. Set `MKT_INTEL_IAP_AUDIENCE` to the IAP audience of the protected resource
   (`/projects/<NUM>/global/backendServices/<ID>` for an HTTPS LB). The adapter verifies
   signature, audience, issuer and expiry against Google's IAP keys; any failure is a 401.
   The assertion is never logged.
3. For a client workforce that lives in a non-Google IdP (Entra ID, Okta, AD FS),
   federate it into IAP with **Workforce Identity Federation**: users sign in against the
   client IdP and IAP still injects the verified assertion. No agent code changes.

The verified subject (email or sub claim) becomes the audit actor on every brief; the
`hd` (hosted-domain) claim maps to the tenant.

## 4. Embed inside an existing portal (same-origin reverse proxy)

Serve the agent under the parent origin at a sub-path, then iframe that path. Because the
frame is first-party there is no CORS to configure and no third-party-cookie issue.

### 4a. Proxy routes (nginx)

```nginx
# On https://portal.client.com
location /market-intel/ {
    proxy_pass         http://mi-ui.internal:3000/;   # the Next.js console
    proxy_set_header   Host $host;
}
location /market-intel/api/ {
    proxy_pass         http://mi-api.internal:8100/;   # the FastAPI backend
    proxy_set_header   Host $host;
    # Behind IAP the assertion header is forwarded automatically on the same origin.
}
```

Or, for a Next.js host app, the equivalent `rewrites()`:

```js
// next.config.mjs of the HOST portal
async rewrites() {
  return [
    { source: "/market-intel/api/:path*", destination: "http://mi-api.internal:8100/:path*" },
    { source: "/market-intel/:path*",     destination: "http://mi-ui.internal:3000/market-intel/:path*" },
  ];
}
```

### 4b. Build the console for the sub-path

```bash
# Build-time env for the market-intelligence UI
NEXT_PUBLIC_BASE_PATH=/market-intel        # mounts routes + assets under /market-intel
NEXT_PUBLIC_API_BASE=/market-intel/api     # API calls stay same-origin through the proxy
NEXT_PUBLIC_EMBED=1                         # host page owns the chrome
NEXT_PUBLIC_FRAME_ANCESTORS="https://portal.client.com"  # who may frame the UI document
```

### 4c. The iframe tag (host page)

```html
<iframe src="/market-intel/" title="Market intelligence"
        style="width:100%;height:900px;border:0"></iframe>
```

### 4d. Allow the parent to frame the agent

Two layers emit the anti-clickjacking policy, and they must agree:

- The **backend** emits `Content-Security-Policy: frame-ancestors <allowlist>` on every
  API response (`api/app.py` middleware), from `MKT_INTEL_FRAME_ANCESTORS`.
- The **UI** is served by Next.js, so the document a browser actually frames carries its
  own header. That policy is built in `ui/lib/csp.mjs` and emitted from `ui/proxy.ts`, from
  `NEXT_PUBLIC_FRAME_ANCESTORS`, read in the same three states as the backend variable.

Both default to `'self'` (and add `X-Frame-Options: SAMEORIGIN` in that case). To allow
specific parent origins set a space-separated list, per the CSP grammar:

`MKT_INTEL_FRAME_ANCESTORS` is read in three states, because a variable you emptied is a
configuration and not an omission:

| State | Result |
|-------|--------|
| unset | `frame-ancestors 'self'` plus `X-Frame-Options: SAMEORIGIN` (the shipped default). |
| set and empty | `frame-ancestors 'none'` plus `X-Frame-Options: DENY`, and a warning is logged. Emptying the allowlist means nobody may frame this, so it tightens; it never inherits the unset default. |
| set to origins | Exactly those origins, whitespace normalised. No `X-Frame-Options` accompanies a named allowlist, because that header cannot express one. |

Before this rule, an empty value went straight into the header, so the response carried
`frame-ancestors` with an empty directive that browsers discard as a parse error, and the
`X-Frame-Options` fallback was skipped as well: the clickjacking control disappeared with
no sign that it had.

```bash
export MKT_INTEL_FRAME_ANCESTORS="https://portal.client.com https://admin.client.com"
# and at UI build time:
export NEXT_PUBLIC_FRAME_ANCESTORS="https://portal.client.com https://admin.client.com"
```

### 4e. The console's own Content-Security-Policy

A console that emits `frame-ancestors` and nothing else has no policy worth the name: no `default-src`, no
`script-src`, no `object-src`, no `base-uri`. It now serves the full default-deny baseline,
built once in `ui/lib/csp.mjs` and emitted from exactly one place, `ui/proxy.ts`:

```
default-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none';
script-src 'self' 'nonce-<per-request>' 'strict-dynamic'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; font-src 'self' data:; connect-src 'self' <API origin>;
frame-ancestors <allowlist>
```

Three things about it are load-bearing:

1. **One emitter.** `next.config.mjs` no longer emits a CSP at all; it carries only the two
   genuinely static headers (`X-Content-Type-Options`, `Referrer-Policy`). Two layers both
   setting a CSP makes the browser intersect them and the stricter wins per directive, which
   is how a nonce-less `script-src` would come back without anyone editing it.
2. **The nonce is per request.** Next serves its hydration bootstrap as an inline script, so
   any `script-src` without a nonce blocks it: `__next_f` never fills, React never attaches,
   and every control on the page becomes dead markup while the headers, the type-check, the
   build and the tests all stay green.
3. **The route must be dynamically rendered.** `app/layout.tsx` sets
   `export const dynamic = "force-dynamic"` for that reason and no other. A statically
   prerendered page was built before the nonce existed, so nothing carries it, and
   `'strict-dynamic'` switches off the `'self'` fallback that had at least been loading the
   chunk scripts: the half-configured state blocks strictly more than no nonce at all.
   `next.config.mjs` refuses to build without that line, and `npm run assert-hydratable`
   starts the built server and asserts every served script tag carries the served nonce.
   A header assertion cannot see this, because the header is byte-identical either way.

`connect-src` widens to the ORIGIN of `NEXT_PUBLIC_API_BASE` when it is absolute; a
same-origin proxy sub-path such as `/agent/api` is already covered by `'self'` and widens
nothing.

When the UI is served cross-origin from the API during development, the CORS allowlist is
`MKT_INTEL_CORS_ORIGINS` (comma-separated, defaults to the localhost dev origins, never
`*`). Same-origin embedding needs no CORS at all.

## 5. The identity contract

- **Any client-supplied actor is ignored.** The API request schema (`BriefRequestModel`)
  has no `actor` field, and the backend would not read one. The audit actor is always the
  verified `Principal.actor` resolved by the active profile's `IdentityPort`
  (`api/security.py` builds a `RequestContext` from the request headers and maps
  `IdentityError` to HTTP 401).
- **The Principal carries entitlement principals and a tenant.** `market-intelligence`'s brief and
  competitor-analysis queries are market/vertical scoped and have no per-user ACL seam
  today, so `principals` is recorded for audit and reserved for future entitlement checks
  (the reference repo shows the pattern of merging them into governed-retrieval ACLs as
  `acl_principals=(*existing, *principals)`).
- **Profiles pick the verifier**: `local` = seeded personas (no auth, offline),
  `gcp`/`platform` = IAP assertion verification, `onprem` = fail-fast placeholder for the
  client's own IdP (OIDC/SAML). The contract test requires a `local` and an `onprem`
  binding for the identity port, like every other port.
- The CLI (`mkt-intel`), demo scripts and eval harness call the domain service directly,
  in-process; the `actor` argument they pass is the audit subject for that trusted local
  entry point, not a network-asserted identity.

## 6. Configuration knobs

| Knob | Default | Meaning |
|------|---------|---------|
| `MKT_INTEL_PROFILE` | (none) | Adapter profile: `local`, `gcp`, `platform`, `onprem`. Unset is refused, not `local`: no dev personas, no CORS dev origins. |
| `MKT_INTEL_IAP_AUDIENCE` | (empty) | Expected IAP JWT audience; required in secure mode. |
| `MKT_INTEL_CORS_ORIGINS` | localhost dev origins | Comma-separated CORS allowlist; never `*`. Set and empty denies every origin rather than falling back to the dev origins. |
| `MKT_INTEL_FRAME_ANCESTORS` | `'self'` | Space-separated CSP `frame-ancestors` allowlist (backend). Set and empty means `'none'`, not the default. |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8100` | API base the console calls (use the proxied path when embedded). |
| `NEXT_PUBLIC_BASE_PATH` | (empty) | Sub-path the console mounts under (blank = standalone). |
| `NEXT_PUBLIC_EMBED` | (unset) | `1` drops the console chrome; host owns the page. |
| `NEXT_PUBLIC_FRAME_ANCESTORS` | `'self'` | CSP `frame-ancestors` the UI document emits (must match the backend). Read in the same three states: unset means `'self'`, set and empty means `'none'`, never an empty directive. |
| `X-Dev-Persona` (header) | first persona | Local profile only: selects a seeded persona. |

## 7. Client integration checklist

- [ ] Choose the shape: embedded same-origin proxy, standalone behind IAP, or local dev.
- [ ] Embedded: add the two proxy routes and the iframe tag on the host page.
- [ ] Embedded: build the UI with `NEXT_PUBLIC_BASE_PATH`, `NEXT_PUBLIC_API_BASE`
      (proxied path), `NEXT_PUBLIC_EMBED=1` and `NEXT_PUBLIC_FRAME_ANCESTORS`.
- [ ] Set `MKT_INTEL_FRAME_ANCESTORS` (backend) and `NEXT_PUBLIC_FRAME_ANCESTORS` (UI) to
      the exact same parent origins that may frame it.
- [ ] Secure mode: enable IAP on the service and set `MKT_INTEL_IAP_AUDIENCE`; federate
      the client IdP via Workforce Identity Federation if it is not Google.
- [ ] Do not send `actor` in any request body; it does not exist in the schema.
- [ ] Local demos: pick a persona in the UI or send `X-Dev-Persona`.

## 8. Security checklist

- [ ] `MKT_INTEL_PROFILE=gcp` set explicitly in production (there is no default; an unset
      variable refuses every end-user request rather than falling back to `local`).
- [ ] IAP enabled on the load balancer; direct ingress to the service blocked, so the
      assertion header cannot be spoofed around the proxy.
- [ ] `MKT_INTEL_IAP_AUDIENCE` matches the protected resource exactly.
- [ ] CORS allowlist is explicit per tenant (never `*`); same-origin embeds need none.
- [ ] `frame-ancestors` lists only the intended parent origins on both the backend and the
      UI; the default stays `'self'`.
- [ ] 401s on unknown/missing identity verified after deploy (`curl` without the assertion
      must fail).
- [ ] Audit records show the verified subject as `actor` for every brief.

## 9. Further layers (in the reference repo, not built here)

The reference implementation, `cdd-sow-research` (`docs/embedding-and-identity.md`
there), documents and partly implements the next layers, which this repo deliberately
leaves out of the current slice:

- **Mode 6 "launch in new tab"**: an OIDC Authorization Code + PKCE login flow
  (`/auth/*` routes) with a self-issued session cookie, for hosts that want a link-out
  instead of an iframe (with a `LaunchInNewTab` prompt and a 401 to `/auth/login` fallback).
- **Cross-origin embedding (modes 4/5)**: a versioned loader / web component, a
  postMessage token handoff, and a bearer/JWKS-verifying identity adapter for hosts that
  cannot run a proxy or federate into IAP.
- **Per-hop hardening**: OAuth2 token exchange (on-behalf-of) plus Workload Identity and
  mTLS toward the shared platform services, DPoP / step-up auth for high-value actions.

All three land on seams that already exist here (`IdentityPort`, the settings-driven
adapter bindings, the env-driven embedding headers), so adopting them later is additive.
