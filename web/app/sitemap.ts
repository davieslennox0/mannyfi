import type { MetadataRoute } from "next";

import { baskets } from "@/lib/baskets";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://mannyfi.xyz";
  const pages = ["", "/guide/", "/faq/", "/terms/", ...baskets.map((b) => `/baskets/${b.id}/`)];
  return pages.map((p) => ({ url: `${base}${p}` }));
}
