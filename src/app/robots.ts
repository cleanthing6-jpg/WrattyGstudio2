import type { MetadataRoute } from "next";

const BASE = (process.env.APP_URL || "https://wratty-gstudio2.onrender.com").replace(/\/+$/, "");

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/dashboard", "/studio", "/history", "/master",
                   "/tune", "/beatlock", "/sign-in", "/sign-up"],
      },
    ],
    sitemap: BASE + "/sitemap.xml",
  };
}
