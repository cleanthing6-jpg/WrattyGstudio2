import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "WraGstudio",
    short_name: "WraGstudio",
    description: "Mix and master your music with the Idan engine.",
    start_url: "/",
    display: "standalone",
    background_color: "#101827",
    theme_color: "#101827",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
