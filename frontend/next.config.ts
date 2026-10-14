import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    // In production build, fail on errors
    ignoreDuringBuilds: false,
  },
  typescript: {
    // In production build, fail on errors
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
