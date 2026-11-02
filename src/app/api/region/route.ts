import { NextResponse } from "next/server";
import { regionFromCountry, plansFor } from "@/lib/pricing";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const override = url.searchParams.get("country");

  // 1. Check for manual override, Cloudflare, or Vercel headers
  let country =
    override ||
    request.headers.get("cf-ipcountry") ||
    request.headers.get("x-vercel-ip-country");

  // 2. If empty (Zevcloud), get the IP from x-forwarded-for and look it up
  if (!country) {
    const forwarded = request.headers.get("x-forwarded-for");
    const ip = forwarded ? forwarded.split(",")[0].trim() : null;

    if (ip && ip !== "127.0.0.1" && ip !== "::1") {
      try {
        const res = await fetch(`https://ipapi.co/${ip}/country/`, { cache: "no-store" });
        if (res.ok) {
          country = (await res.text()).trim();
        }
      } catch (e) {
        // Fails silently, defaults to INTL
      }
    }
  }

  const region = regionFromCountry(country);
  
  return NextResponse.json(
    { 
      country: (country || "").toUpperCase() || null, 
      region, 
      plans: plansFor(region) 
    },
    { headers: { "cache-control": "no-store" } }
  );
}