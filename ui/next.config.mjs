/** @type {import('next').NextConfig} */
// NEXT_PUBLIC_BASE_PATH mounts the UI (and its assets) under a reverse-proxy sub-path
// (e.g. /agent) so it can embed same-origin in a host app; blank keeps it standalone.
//
// The Content-Security-Policy is deliberately NOT here. It is built in `lib/csp.mjs` and emitted
// once, from `proxy.ts`, because it carries a per-request nonce and this static `headers()` table
// cannot express one. Emitting a CSP from both layers would give the browser two policies to
// intersect, and the stricter wins per directive, which is exactly how a nonce-less `script-src`
// would come back and block Next's inline hydration bootstrap. Only the two headers that really
// are static live here.
import { readFileSync } from "node:fs";

import { assertHydratableCsp } from "./lib/csp.mjs";

// Refuse the build outright if the nonce policy and the rendering mode disagree: a nonce on a
// statically prerendered route blocks strictly MORE than no nonce at all, and nothing cheaper
// than a running browser can see it.
assertHydratableCsp(readFileSync(new URL("./app/layout.tsx", import.meta.url), "utf8"));

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
