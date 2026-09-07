import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
