import { NextResponse } from "next/server";
import { regionFromCountry, plansFor } from "@/lib/pricing";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const override = url.searchParams.get("country");

  let country =
    override ||
    request.headers.get("cf-ipcountry") ||
    request.headers.get("x-vercel-ip-country");

  if (!country) {
    const forwarded = request.headers.get("x-forwarded-for");
    const realIp = request.headers.get("x-real-ip");
    const ip = forwarded ? forwarded.split(",")[0].trim() : realIp;

    if (ip && ip !== "127.0.0.1" && ip !== "::1" && !ip.startsWith("10.")) {
      try {
        // Use api.country.is - fast, reliable, no rate limits
        const res = await fetch(`https://api.country.is/${ip}`, { 
          cache: "no-store",
          signal: AbortSignal.timeout(2000) // 2 second timeout so it never hangs
        });
        if (res.ok) {
          const data = await res.json();
          country = data.country; // returns "NG", "US", etc.
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
