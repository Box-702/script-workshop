import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @type {import('next').NextConfig} */
const createNextConfig = (phase) => ({
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || (phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next"),
  async rewrites() {
    // Skip the /api -> backend rewrite at build time. Next.js validates
    // every rewrite entry's destination eagerly during `next build`, so a
    // missing or unparseable BACKEND_URL at build time would fail the
    // entire build. Instead we expose a runtime helper that the client
    // (and any server component that needs to call the API) reads via
    // NEXT_PUBLIC_API_BASE, and the actual fetch happens against
    // `${NEXT_PUBLIC_API_BASE}/...` which the browser resolves through
    // our own middleware... but we don't have middleware. Simpler:
    //   - if BACKEND_URL is set, use it for the rewrite
    //   - if not, omit the rewrite so build doesn't fail; the Next.js
    //     app still works (the dev server / runtime will surface the
    //     missing proxy as a fetch error, which is the correct signal
    //     to fix the env var).
    const backend = (process.env.BACKEND_URL || "").trim();
    if (!backend) return [];
    return [
      { source: "/api/:path*", destination: `${backend.replace(/\/+$/, "")}/api/:path*` },
    ];
  },
});

export default createNextConfig;
