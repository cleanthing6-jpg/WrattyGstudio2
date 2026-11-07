import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { findPlanById } from "@/lib/pricing";

const NOWPAYMENTS_ENDPOINT = "https://api.nowpayments.io/v1/invoice";

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { tier } = await req.json();
    const plan = findPlanById(tier);
    
    if (!plan) return NextResponse.json({ error: "Invalid tier" }, { status: 400 });

    const amountUSD = plan.usd;
    if (amountUSD === 0) return NextResponse.json({ error: "Free tier cannot be purchased" }, { status: 400 });

    const apiKey = process.env.NOWPAYMENTS_API_KEY;
    if (!apiKey) return NextResponse.json({ error: "Payment provider not configured" }, { status: 500 });

    const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
    const orderId = `b2c_${userId}_${tier}_${Date.now()}`;

    const res = await fetch(NOWPAYMENTS_ENDPOINT, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        price_amount: amountUSD,
        price_currency: "usd",
        order_id: orderId,
        order_description: `WraGstudio B2C - ${tier} package`,
        ipn_callback_url: new URL("/api/crypto-webhook", appUrl).toString(),
        success_url: new URL("/dashboard", appUrl).toString(),
        cancel_url: new URL("/pricing", appUrl).toString(),
      }),
      cache: "no-store",
    });

    const data = await res.json();
    if (!res.ok || !data.invoice_url) {
      console.error("NOWPayments B2C Error:", data);
      return NextResponse.json({ error: "Failed to create crypto invoice" }, { status: 502 });
    }

    return NextResponse.json({ url: data.invoice_url });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
