import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Cloud deployment — full Next.js server mode
  // "standalone" emits a self-contained server for the Docker image (Hostinger VPS)
  output: "standalone",
  // no image optimisation server needed
  images: { unoptimized: true },
  // lint in dev, not in the production image build — the eslint-config-next
  // ESM resolution is environment-sensitive and must never block a deploy
  eslint: { ignoreDuringBuilds: true },
}

export default nextConfig
