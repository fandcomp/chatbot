import type { NextConfig } from "next";

// Static (non-nonce) CSP — see docs/adr and .claude/rules/web/security.md.
// A nonce-based script-src was considered (the rules file's own example),
// but Next.js requires ALL pages to opt into dynamic rendering to support
// per-request nonces (see node_modules/next/dist/docs/.../content-security-
// policy.md "Dynamic Rendering Requirement") — a much bigger, separate
// performance trade-off than this hardening pass should make silently
// (disables static optimization/ISR app-wide). Documented as a deferred
// follow-up in docs/KNOWN_LIMITATIONS.md.
//
// script-src needs 'unsafe-inline': Next.js injects its own inline
// bootstrap <script> tags (hydration payload / chunk-loading setup) on
// EVERY page, in both dev and production — confirmed live via a real
// `next build && next start` run, not just `next dev`: without
// 'unsafe-inline' the browser's own CSP silently blocks those scripts,
// React never hydrates, and every click on a submit button falls through
// to a native, JS-free HTML form submission instead of ever reaching a
// React onSubmit handler (this is exactly the shape of bug it caused —
// no visible error, just a page that "does nothing" on submit). The
// browser-reported violations named exact sha256 hashes for the blocked
// scripts, which raised hash-based allowlisting as an alternative to
// 'unsafe-inline' — rejected because Next.js's hydration payload script
// embeds page-specific data, so its hash is not stable across routes or
// even across requests to the same route, making a hash allowlist
// impractical to keep correct. The residual risk 'unsafe-inline' accepts
// (injected inline script execution) is mitigated the same way this
// codebase already defends against XSS generally: React escapes all
// rendered content by default, and no `dangerouslySetInnerHTML` exists
// anywhere in apps/web/src (verified 2026-09 audit) — so CSP here is a
// second layer on top of that, not the only one.
// style-src keeps 'unsafe-inline' because @base-ui/react/shadcn primitives
// (used throughout apps/web) set inline `style` attributes at runtime for
// positioning — blocking that would break every popover/dropdown/dialog.
const isDev = process.env.NODE_ENV === "development";
const cspHeader = `
  default-src 'self';
  script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""};
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:;
  font-src 'self';
  connect-src 'self';
  object-src 'none';
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
`
  .replace(/\s{2,}/g, " ")
  .trim();

const securityHeaders = [
  { key: "Content-Security-Policy", value: cspHeader },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // Excludes /api: those responses come from the proxied FastAPI
        // backend (see rewrites() below) and must keep the backend's own
        // response headers untouched rather than being overwritten here.
        source: "/((?!api).*)",
        headers: securityHeaders,
      },
    ];
  },
  // Next.js dev mode blocks cross-origin requests for its own JS chunks/HMR
  // by default (DNS-rebinding protection) — without this, a page loaded
  // through the demo tunnel returns 200 for the HTML shell but every script
  // chunk is blocked, so React never hydrates and the page looks "stuck"
  // (forms do nothing; nothing is actually broken server-side). Wildcarded
  // so a fresh `cloudflared tunnel --url` subdomain (a new one every run,
  // per scripts/start-demo-tunnel.sh) never needs this file edited again.
  allowedDevOrigins: ["*.trycloudflare.com"],
  // Proxies the browser's API calls through this same origin to the local
  // FastAPI dev server, so a tunnel exposing only this app (e.g. ngrok) still
  // works end-to-end — the session cookie is SameSite=Lax, which browsers
  // never send on a genuinely cross-origin request to a separate backend URL.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
