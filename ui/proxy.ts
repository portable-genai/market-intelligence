// The one place a per-request CSP nonce is minted and attached, on Next 16's `proxy` hook
// (the successor to `middleware`).
//
// Both header sets below are required, and each is useless alone:
//
//   * The REQUEST header is where Next reads the nonce it stamps onto every `<script>` tag it
//     emits. Setting only this proves nothing to the browser, which never sees it.
//   * The RESPONSE header is what the browser actually enforces. Setting only this blocks the
//     very inline hydration bootstrap the nonce was added to allow.
//
// The request header name must be exactly `Content-Security-Policy`; Next matches on it.

import { type NextRequest, NextResponse } from "next/server";

import { contentSecurityPolicy, frameAncestors, frameOptions, generateNonce } from "./lib/csp.mjs";

export function proxy(request: NextRequest) {
  const nonce = generateNonce();
  const csp = contentSecurityPolicy(process.env, nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);

  // Only for the two framing policies X-Frame-Options can express; a named allowlist has no
  // spelling there, so nothing is sent rather than a SAMEORIGIN that contradicts the CSP.
  const legacy = frameOptions(frameAncestors(process.env));
  if (legacy) response.headers.set("X-Frame-Options", legacy);

  return response;
}

export const config = { matcher: "/:path*" };
