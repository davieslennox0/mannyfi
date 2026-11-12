import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Served as plain files by Caddy: no Node process on the box.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  /* config options here */
  // cacheComponents / partialPrefetching (scaffold defaults) are incompatible with static export.
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
