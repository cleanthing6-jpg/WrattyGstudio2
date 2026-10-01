import { NextResponse } from "next/server";
import { regionFromCountry, plansFor } from "@/lib/pricing";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  // Cloudflare (you already use it) sends CF-IPCountry on every request.
  // ?country=XX overrides for testing.
  const url = new URL(request.url);
  const override = url.searchParams.get("country");
  const country =
    override ||
    request.headers.get("cf-ipcountry") ||
    request.headers.get("x-vercel-ip-country") ||
    "";

  const region = regionFromCountry(country);
  return NextResponse.json(
    { country: country.toUpperCase() || null, region, plans: plansFor(region) },
    { headers: { "cache-control": "no-store" } }
  );
}
