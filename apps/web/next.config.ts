import type { NextConfig } from "next";

// The browser talks to the API through /api on the web origin, so auth cookies are
// first-party and same-origin. API_URL points at the FastAPI service.
const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // The persistent dev cache kept serving stylesheets without Tailwind classes
    // added since the last cold start (see README). Dev restarts are fast enough
    // without it; production builds keep their cache.
    turbopackFileSystemCacheForDev: false,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
