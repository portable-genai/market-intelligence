import type { Metadata } from "next";
import "./globals.css";

// Required by the nonce CSP, not a performance preference. `proxy.ts` mints a per-request
// script nonce and Next can only stamp it onto the script tags of a DYNAMICALLY rendered route.
// A statically prerendered page was built before the nonce existed, so it would serve bare
// script tags against a header advertising a nonce, and `'strict-dynamic'` switches off the
// `'self'` fallback that was at least loading the chunks: strictly worse than no nonce at all.
// `next.config.mjs` refuses to build without this line.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "D1 Market Intelligence",
  description:
    "Cited market briefs and competitor analysis from grounded deep research and an internal corpus, generic across banking and online retail and the JP/AU/SG markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // EMBED mode: when the UI is dropped into a host app's page, the host owns the chrome,
  // so render children directly with no wrapper of our own.
  const embed = process.env.NEXT_PUBLIC_EMBED === "1";
  return (
    <html lang="en">
      <body className="min-h-screen">
        {embed ? <main className="p-4">{children}</main> : children}
      </body>
    </html>
  );
}
