import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Cloud deployment (Hostinger VPS) — full Next.js server mode
  // images.unoptimized avoids needing a separate image-optimisation server
  images: { unoptimized: true },
}

export default nextConfig
