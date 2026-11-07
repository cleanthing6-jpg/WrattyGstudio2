import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MONEI_ENDPOINT = "https://api.monei.cc/api/v1/wallet/deposit/payment-link";

type PackageType = "mix" | "master";

const PACKAGES: Record<PackageType, { usd: number; credits: number }> = {
  master: { usd: 1000, credits: 1000 },
  mix: { usd: 2500, credits: 1000 },
};

type JsonObject = Record<string, unknown>;

const isObject = (v: unknown): v is JsonObject =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function extractCheckoutUrl(body: unknown): string | null {
  if (!isObject(body) || !isObject(body.data)) return null;
  const link = body.data.link;
  return typeof link === "string" && link.startsWith("https://") ? link : null;
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const apiKey = process.env.MONEI_API_KEY;
  const secretKey = process.env.MONEI_SECRET_KEY;
  if (!apiKey || !secretKey) {
    return NextResponse.json({ error: "Payment provider not configured" }, { status: 500 });
  }

  let packageType: unknown;
  try {
    ({ packageType } = (await req.json()) as { packageType?: unknown });
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (packageType !== "mix" && packageType !== "master") {
    return NextResponse.json({ error: "Invalid package type" }, { status: 400 });
  }

  const pkg = PACKAGES[packageType];
  const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";

  const payload = {
    amount: pkg.usd,
    currency: "USD",
    narration: `api_credits|user:${userId}|pkg:${packageType}|credits:${pkg.credits}`,
    redirectUrl: new URL("/developers", appUrl).toString(),
  };

  try {
    const res = await fetch(MONEI_ENDPOINT, {
      method: "POST",
      headers: {
        "X-API-KEY": apiKey,
        "X-API-SECRET": secretKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });

    const raw = await res.text();
    let data: unknown = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = null;
    }

    if (!res.ok) {
      return NextResponse.json({ error: "Failed to create payment link" }, { status: res.status });
    }

    const url = extractCheckoutUrl(data);
    
    if (!url) {
      return NextResponse.json({ error: "Payment provider returned an unexpected response" }, { status: 502 });
    }

    return NextResponse.json({ url });
  } catch (err) {
    return NextResponse.json({ error: "Could not reach payment provider" }, { status: 502 });
  }
}
