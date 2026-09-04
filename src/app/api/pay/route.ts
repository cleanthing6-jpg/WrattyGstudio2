import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  try {
    const { email, amount, tier } = await req.json();
    const response = await fetch("https://api.paystack.co/transaction/initialize", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}` },
      body: JSON.stringify({ email, amount: amount * 100, metadata: { tier }, callback_url: "http://localhost:3000/dashboard" }),
    });
    const data = await response.json();
    if (data.status) return NextResponse.json({ authorization_url: data.data.authorization_url });
    return NextResponse.json({ error: "Payment failed" }, { status: 500 });
  } catch (e: unknown) { return NextResponse.json({ error: e instanceof Error ? e.message : "Request failed" }, { status: 500 }); }
}
