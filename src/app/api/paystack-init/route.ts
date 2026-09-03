import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
const PRICES: Record<string, number> = { starter: 300000, pro: 700000, studio: 1400000 };
export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { tier } = await req.json();
  const amount = PRICES[tier];
  if (!amount) return NextResponse.json({ error: "Invalid tier" }, { status: 400 });
  const res = await fetch("https://api.paystack.co/transaction/initialize", {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email: `${userId}@wrattyg.app`, amount, callback_url: `${process.env.NEXT_PUBLIC_APP_URL || "https://wrattygstudio.vercel.app"}/api/paystack-verify?tier=${tier}`, metadata: { userId, tier } }),
  });
  const data = await res.json();
  return NextResponse.json({ url: data.data?.authorization_url || null });
}
