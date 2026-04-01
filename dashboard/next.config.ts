import type { NextConfig } from "next";

const backend = process.env.AGENTIVA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/dashboard",
        headers: [
          {
            key: "Cache-Control",
            value: "private, no-store, must-revalidate",
          },
        ],
      },
      {
        source: "/dashboard/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "private, no-store, must-revalidate",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      // Do NOT rewrite `/api/auth/*` — Auth.js lives on Next.js.
      // Agentiva API: `app/api/v1/[...path]/route.ts` (JWT + proxy).
      {
        source: "/health",
        destination: `${backend}/health`,
      },
    ];
  },
};

export default nextConfig;
