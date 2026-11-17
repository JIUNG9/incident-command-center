/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",  // for k8s container deploy
  // Proxy /api/* to the vigil-chat-api service in-cluster
  async rewrites() {
    const apiUrl = process.env.VIGIL_CHAT_API_URL || "http://vigil-chat-api.vigil-agent.svc.cluster.local";
    const warUrl = process.env.VIGIL_WAR_API_URL  || "http://vigil-war-api.vigil-agent.svc.cluster.local";
    return [
      { source: "/api/chat/:path*", destination: `${apiUrl}/:path*` },
      { source: "/api/war/:path*",  destination: `${warUrl}/:path*` },
    ];
  },
};
export default nextConfig;
