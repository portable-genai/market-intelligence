// Unit cover for the parts of the CSP a STRING can decide, and nothing more.
//
// These tests are NOT sufficient, and the reason is the whole point of `scripts/assert-hydratable.mjs`.
// The defect that shipped a dead console had a byte-perfect CSP header: nonce present,
// `'strict-dynamic'` present, every directive correct. What was wrong was the rendered MARKUP,
// which carried no nonce because the route was statically prerendered. No assertion over this
// string can see that. Only starting the built server and reading the document can, which is what
// `npm run assert-hydratable` does, last in the ui gate, against the artefact `next build` made.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  UnhydratableCspError,
  WildcardOriginError,
  assertHydratableCsp,
  contentSecurityPolicy,
  frameAncestors,
  frameOptions,
  generateNonce,
} from "../lib/csp.mjs";

/** Split a policy string into a directive -> value map. */
function directives(csp) {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...value] = part.split(/\s+/);
        return [name, value.join(" ")];
      }),
  );
}

test("the policy carries every directive the baseline requires", () => {
  const d = directives(contentSecurityPolicy({}, "n0nce"));
  for (const name of [
    "default-src",
    "base-uri",
    "form-action",
    "object-src",
    "script-src",
    "style-src",
    "img-src",
    "font-src",
    "connect-src",
    "frame-ancestors",
  ]) {
    assert.ok(d.has(name), `missing ${name}`);
  }
  assert.equal(d.get("object-src"), "'none'");
  assert.equal(d.get("base-uri"), "'self'");
});

test("no directive is ever emitted empty, in any state of the framing variable", () => {
  // An empty directive is a CSP parse error: browsers discard it, so the restriction silently
  // disappears. That is how a `frame-ancestors` with a blanked allowlist removed clickjacking
  // protection altogether rather than tightening it.
  for (const env of [{}, { NEXT_PUBLIC_FRAME_ANCESTORS: "" }, { NEXT_PUBLIC_FRAME_ANCESTORS: "  " }]) {
    for (const [name, value] of directives(contentSecurityPolicy(env, "n0nce"))) {
      assert.notEqual(value, "", `${name} is empty for env ${JSON.stringify(env)}`);
    }
  }
});

test("script-src takes the nonce and 'strict-dynamic' only when a nonce is supplied", () => {
  assert.equal(
    directives(contentSecurityPolicy({}, "abc123")).get("script-src"),
    "'self' 'nonce-abc123' 'strict-dynamic'",
  );
  assert.equal(directives(contentSecurityPolicy({})).get("script-src"), "'self'");
});

test("frame-ancestors is three-state, mirroring the backend's _frame_ancestors", () => {
  // Unset keeps the shipped default; set-but-naming-nothing means "nobody may frame this", which
  // is spelled 'none'; otherwise the named origins, whitespace-normalised.
  assert.equal(frameAncestors({}), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "" }), "'none'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "   " }), "'none'");
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.bank.example  https://admin.bank.example" }),
    "https://portal.bank.example https://admin.bank.example",
  );
});

test("X-Frame-Options is sent only for the two policies it can express", () => {
  assert.equal(frameOptions("'self'"), "SAMEORIGIN");
  assert.equal(frameOptions("'none'"), "DENY");
  assert.equal(frameOptions("https://portal.bank.example"), "");
});

test("connect-src widens to the API ORIGIN, never the full URL", () => {
  const d = directives(
    contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "https://api.bank.example:8443/v1/briefs" }, "n"),
  );
  assert.equal(d.get("connect-src"), "'self' https://api.bank.example:8443");
});

test("a same-origin proxy sub-path widens nothing and is not a misconfiguration", () => {
  // `NEXT_PUBLIC_API_BASE=/agent/api` is the documented same-origin embedding setup; 'self'
  // already covers it, so it must neither be added as an origin nor throw.
  const d = directives(contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "/agent/api" }, "n"));
  assert.equal(d.get("connect-src"), "'self'");
  assert.throws(
    () => contentSecurityPolicy({ NEXT_PUBLIC_API_BASE: "api.bank.example" }, "n"),
    /must be an absolute URL or a path/,
  );
});

test("nonces are unique and base64", () => {
  const seen = new Set();
  for (let i = 0; i < 50; i += 1) {
    const nonce = generateNonce();
    assert.match(nonce, /^[A-Za-z0-9+/]+={0,2}$/);
    seen.add(nonce);
  }
  assert.equal(seen.size, 50);
});

test("the build refuses a nonce policy on a statically prerendered layout", () => {
  assert.throws(
    () => assertHydratableCsp("export const metadata = {};\n"),
    UnhydratableCspError,
  );
  assert.doesNotThrow(() => assertHydratableCsp('export const dynamic = "force-dynamic";\n'));
});

test("a wildcard frame-ancestors is refused in every spelling a config can render", () => {
  // The FastAPI half already refuses these. This is the OTHER emitter, and it is the one a
  // browser honours for the document, so closing only the service side left the console
  // framable by any origin while every check stayed green.
  for (const wildcard of ["*", "'*'", "null", "*.*"]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }),
      WildcardOriginError,
      `${JSON.stringify(wildcard)} must be refused, not passed through to the header`,
    );
  }
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example *" }),
    WildcardOriginError,
    "a wildcard standing beside named origins is still a wildcard",
  );
  assert.throws(
    () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "*,https://portal.client.example" }),
    WildcardOriginError,
    "a comma is not CSP list syntax, so a comma-joined wildcard must still be seen",
  );
  // A HOST-SOURCE wildcard is the spelling an exact-token set misses, and CSP honours it: every
  // subdomain may frame the console, including one an attacker takes over or registers on a
  // user-content domain. A real origin never contains an asterisk, so refusing the character
  // outright turns away nothing a deployment could correctly hold.
  for (const hostSource of [
    "https://*.client.example",
    "*.client.example",
    "https://*",
    "https://portal.client.example https://*.evil.example",
  ]) {
    assert.throws(
      () => frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: hostSource }),
      WildcardOriginError,
      `${JSON.stringify(hostSource)} is a host-source wildcard and must be refused`,
    );
  }
});

test("the policy the proxy actually serves refuses a wildcard too", () => {
  // `contentSecurityPolicy` is what `proxy.ts` puts on the document response. Refusing inside
  // the resolver alone would be theatre if this path could still build a policy around it.
  for (const wildcard of ["*", "'*'", "null", "*.*", "https://*.client.example"]) {
    assert.throws(
      () => contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: wildcard }, "n0nce"),
      WildcardOriginError,
      `the served document policy must not carry frame-ancestors ${wildcard}`,
    );
  }
});

test("a legitimate named allowlist is unaffected by the wildcard refusal", () => {
  // A refusal that also refuses valid input is an outage, not a control.
  assert.equal(
    frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }),
    "https://portal.client.example",
  );
  assert.equal(
    frameAncestors({
      NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example https://intranet.client.example",
    }),
    "https://portal.client.example https://intranet.client.example",
  );
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'self'" }), "'self'");
  assert.equal(frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: "'none'" }), "'none'");
  assert.match(
    contentSecurityPolicy({ NEXT_PUBLIC_FRAME_ANCESTORS: "https://portal.client.example" }, "n"),
    /frame-ancestors https:\/\/portal\.client\.example/,
  );
});

test("the unset and emptied states are exactly what they were before wildcards were refused", () => {
  // Pinned so a later edit cannot drift them. THIS repo maps an emptied value to 'none' rather
  // than refusing it, mirroring its own FastAPI half; the wildcard case is an addition to that
  // behaviour, never a replacement for it, and 'none' is the one answer a wildcard is not.
  assert.equal(frameAncestors({}), "'self'");
  for (const blank of ["", "   ", "\t", "\n", " \t\n "]) {
    assert.equal(
      frameAncestors({ NEXT_PUBLIC_FRAME_ANCESTORS: blank }),
      "'none'",
      `blank value ${JSON.stringify(blank)} must still resolve to the lockdown value`,
    );
  }
  assert.equal(frameOptions("'none'"), "DENY");
});
