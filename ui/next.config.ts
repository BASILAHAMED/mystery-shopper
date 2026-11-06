import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  // Static export cannot use the Next.js image optimizer.
  images: { unoptimized: true },
};

export default nextConfig;
