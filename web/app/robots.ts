import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/approve", "/sign", "/connect", "/portfolio", "/fund", "/trading"] }],
    sitemap: "https://mannyfi.xyz/sitemap.xml",
  };
}
