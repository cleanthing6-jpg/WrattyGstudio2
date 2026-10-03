import type { MetadataRoute } from "next";

const BASE = (process.env.APP_URL || "https://wratty-gstudio2.onrender.com").replace(/\/+$/, "");

// Public pages only - nothing behind auth.
export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/pricing", "/terms", "/privacy", "/refund", "/support"].map((r) => ({
    url: BASE + r,
    lastModified: new Date(),
  }));
}
