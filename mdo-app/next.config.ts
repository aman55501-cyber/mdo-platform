import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Cloud deployment — full Next.js server mode
  // "standalone" emits a self-contained server for the Docker image (Hostinger VPS)
  output: "standalone",
  // no image optimisation server needed
  images: { unoptimized: true },
}

export default nextConfig
