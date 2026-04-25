import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Cloud deployment (Railway) — full Next.js server mode
  // images.unoptimized kept for Railway free tier (no image optimisation server needed)
  images: { unoptimized: true },
}

export default nextConfig
