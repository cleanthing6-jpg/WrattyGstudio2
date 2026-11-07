import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import getMongoClient from "@/lib/mongodb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MONEI_ENDPOINT = "https://api.monei.cc/api/v1/wallet/deposit/payment-link";
const REDIRECT_URL = "https://wrattygstudio2.zevcloud.app/developers";

type JsonObject = Record<string, unknown>;

const isObject = (v: unknown): v is JsonObject =>
  typeof v === "object" && v !== null && !Array.isArray(v);

// Candidate property names for the checkout link (unverified, checked in order)
const LINK_KEYS = [
  "paymentLink",
  "payment_link",
  "url",
  "link",
  "checkoutUrl",
  "checkout_url",
  "paymentUrl",
  "payment_url",
  "authorization_url",
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

  const topLevel = pickLink(body);
  if (topLevel) return topLevel;

  if (isObject(body.data)) {
    const nested = pickLink(body.data);
    if (nested) return nested;
  }
  return null;
}

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // 1. Verify the developer has a profile
    const client = await getMongoClient();
    const db = client.db();
    const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
    if (!profile) {
      return NextResponse.json({ error: "Please verify your company first." }, { status: 403 });
    }

    // 2. Get packageType from frontend and calculate amount
    const body = await req.json();
    const packageType = body.packageType || "mix";
    const amount = packageType === "master" ? 1000 : 2500;

    const apiKey = process.env.MONEI_API_KEY;
    const secretKey = process.env.MONEI_SECRET_KEY;
    if (!apiKey || !secretKey) {
      console.error("[buy-crypto] Missing MONEI_API_KEY or MONEI_SECRET_KEY");
      return NextResponse.json({ error: "Payment provider not configured" }, { status: 500 });
    }

    // 3. Format narration so the webhook can parse it later
    const narration = `b2b_${userId}_${packageType}_${Date.now()}`;

    const payload = {
      amount,
      currency: "USD",
      narration,
      redirectUrl: REDIRECT_URL,
    };

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
      console.error("[buy-crypto] Monei error", res.status, raw);
      const message =
        isObject(data) && typeof data.message === "string"
          ? data.message
          : Array.isArray((data as JsonObject | null)?.message)
            ? ((data as JsonObject).message as string[]).join(", ")
            : "Failed to create payment link";
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
  } catch (err: any) {
    console.error("[buy-crypto] Request failed", err);
    return NextResponse.json({ error: err.message || "Could not reach payment provider" }, { status: 502 });
  }
}
