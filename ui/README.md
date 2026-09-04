# `market-intelligence` Market Intelligence: Demo UI

A thin demo console for `market-intelligence`, the Market Intelligence and Competitor Analysis system. It
is a thin presentation layer over the `market-intelligence` FastAPI backend: it builds a cited market brief for
a topic in a chosen market and vertical, and renders the audit-first result (summary, key
claims with provenance, trend scores, the deterministic competitor-move diff, the ranked
where-to-play options, and the source list) with the maker-checker "human review required"
banner. It never bypasses the guardrail or the review gate: it only shows what the backend
returns.

Built with **Next.js (App Router) + TypeScript + Tailwind**. Dependencies are kept minimal:
`next`, `react`, `react-dom`, `tailwindcss`, `postcss`, `autoprefixer`, `typescript`, and the
`@types` packages, nothing else.

## Generic and APAC

The market selector covers **Japan / Australia / Singapore** (each labelled with its
residency region), and the vertical selector covers **banking** and **online retail**. The
console is vertical-agnostic: it renders whatever the backend returns for the selected
market and vertical.

## Configure the backend

Nothing to configure to run against `make run-api`: `NEXT_PUBLIC_API_BASE` already
defaults to the `market-intelligence` API port 8100. Write the override yourself only when the API is
somewhere else, and write it before `npm run build`, because Next inlines every
`NEXT_PUBLIC_*` value at build time:

```bash
echo 'NEXT_PUBLIC_API_BASE=https://api.elsewhere.example' > .env.local
```

## Run

```bash
# 1. start the `market-intelligence` API (from the repo root)
make run-api            # uvicorn on :8100, PROFILE=local by default

# 2. start the console
make run-ui             # or: cd ui && npm install && npm run dev
```

Then open http://localhost:3000.

## Source map

| Path | What lives there |
|------|------------------|
| `app/` | The App Router entry: `layout.tsx` (chrome, and the `force-dynamic` the nonce CSP requires) and `page.tsx`. |
| `components/` | `BriefView` and `CitationList`, the audit-first render of what the backend returned. |
| `lib/api.ts` | The typed fetch layer against `NEXT_PUBLIC_API_BASE`. |
| `lib/csp.mjs` | The ONE place the Content-Security-Policy is built. Read by `proxy.ts` and `next.config.mjs`; never duplicated. |
| `proxy.ts` | Mints the per-request script nonce and sets the CSP on both the request headers (where Next reads the nonce to stamp) and the response headers (what the browser enforces). |
| `next.config.mjs` | Base path, and the two genuinely static headers. Emits NO CSP, and refuses the build if the layout is not dynamically rendered. |
| `scripts/assert-hydratable.mjs` | Starts the BUILT server and asserts the served document hydrates. |
| `tests/csp.test.mjs` | Unit cover for what the policy STRING can decide, which is deliberately less than you would hope. |

## Gate

```bash
make ui-install     # npm ci, exactly as CI installs
make ui-check       # tsc --noEmit, node --test, next build, assert-hydratable
```

`assert-hydratable` runs last and against the artefact `next build` just produced, because it
is the only check that executes the page. Every cheaper check passes in the broken case: the
CSP header is byte-identical whether or not the served script tags carry its nonce, and a
console whose React never attached renders, type-checks, builds and screenshots exactly like a
working one while none of its controls do anything.
