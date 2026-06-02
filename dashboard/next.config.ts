import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin({
  requestConfig: "./src/i18n/request.ts",
});

// For OSS demo: point CHAT_API_URL at your local `vigil serve` (defaults to :8080)
const CHAT_API_URL = process.env.CHAT_API_URL || "http://localhost:8080";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  env: { CHAT_API_URL },
  async rewrites() {
    return [
      { source: "/api/chat-proxy/:path*", destination: `${CHAT_API_URL}/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
