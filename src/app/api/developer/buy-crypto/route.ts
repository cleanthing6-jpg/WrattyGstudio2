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

interface MoneiPaymentLinkPayload {
  amount: number;
  currency: "USD";
  narration: string;
  redirectUrl: string;
}

type JsonObject = Record<string, unknown>;

const isObject = (v: unknown): v is JsonObject =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const LINK_KEYS = [
  "paymentLink", "payment_link", "url", "link",
  "checkoutUrl", "checkout_url", "paymentUrl", "payment_url", "authorization_url",
] as const;

function pickLink(obj: JsonObject): string | null {
  for (const key of LINK_KEYS) {
    const value = obj[key];
    if (typeof value === "string" && value.startsWith("http")) return value;
  }
  return null;
}

function extractCheckoutUrl(body: unknown): string | null {
  if (!isObject(body)) return null;
  const top = pickLink(body);
  if (top) return top;
  if (isObject(body.data)) return pickLink(body.data);
  return null;
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const apiKey = process.env.MONEI_API_KEY;
  const secretKey = process.env.MONEI_SECRET_KEY;
  if (!apiKey || !secretKey) {
    console.error("[buy-crypto] Missing MONEI_API_KEY or MONEI_SECRET_KEY");
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

  const payload: MoneiPaymentLinkPayload = {
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
    
    // --- ADDED THIS LOG ---
    console.log("[buy-crypto] Monei raw response:", raw);
    // ----------------------

    let data: unknown = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = null;
    }

    if (!res.ok) {
      console.error("[buy-crypto] Monei error", res.status, raw);
      let message = "Failed to create payment link";
      if (isObject(data)) {
        if (typeof data.message === "string") message = data.message;
        else if (Array.isArray(data.message)) message = data.message.join(", ");
      }
      return NextResponse.json({ error: message }, { status: res.status });
    }

    const url = extractCheckoutUrl(data);
    if (!url) {
      console.error("[buy-crypto] No checkout URL found in Monei response:", raw);
      return NextResponse.json(
        { error: "Payment provider returned an unexpected response" },
        { status: 502 }
      );
    }

    return NextResponse.json({ url });
  } catch (err) {
    console.error("[buy-crypto] Request failed", err);
    return NextResponse.json({ error: "Could not reach payment provider" }, { status: 502 });
  }
}
