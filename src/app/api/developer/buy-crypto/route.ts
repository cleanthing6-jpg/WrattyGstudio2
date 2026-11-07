import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NOWPAYMENTS_ENDPOINT = "https://api.nowpayments.io/v1/invoice";

type PackageType = "mix" | "master";

const PACKAGES: Record<PackageType, { usd: number; credits: number }> = {
  master: { usd: 1000, credits: 1000 },
  mix: { usd: 2500, credits: 1000 },
};

interface InvoiceResponse {
  id?: string | number;
  invoice_url?: string;
  message?: string;
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const apiKey = process.env.NOWPAYMENTS_API_KEY;
  if (!apiKey) {
    console.error("[buy-crypto] Missing NOWPAYMENTS_API_KEY");
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
  const orderId = `${userId}|${packageType}|${Date.now()}`;

  try {
    const res = await fetch(NOWPAYMENTS_ENDPOINT, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        price_amount: pkg.usd,
        price_currency: "usd",
        order_id: orderId,
        order_description: `API credits (${packageType}) - ${pkg.credits} credits`,
        ipn_callback_url: new URL("/api/crypto-webhook", appUrl).toString(),
        success_url: new URL("/developers", appUrl).toString(),
        cancel_url: new URL("/developers", appUrl).toString(),
      }),
      cache: "no-store",
    });

    const data = (await res.json().catch(() => null)) as InvoiceResponse | null;

    if (!res.ok || !data?.invoice_url) {
      console.error("[buy-crypto] NOWPayments error", res.status, JSON.stringify(data));
      return NextResponse.json(
        { error: data?.message || "Failed to create crypto invoice" },
        { status: res.ok ? 502 : res.status }
      );
    }

    return NextResponse.json({ url: data.invoice_url });
  } catch (err) {
    console.error("[buy-crypto] Request failed", err);
    return NextResponse.json({ error: "Could not reach payment provider" }, { status: 502 });
  }
}
