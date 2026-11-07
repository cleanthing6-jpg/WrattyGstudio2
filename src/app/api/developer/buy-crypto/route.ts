import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const client = await getMongoClient();
    const db = client.db();
    const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
    if (!profile) return NextResponse.json({ error: "Please verify your company first." }, { status: 403 });

    const body = await req.json();
    const packageType = body.packageType || "mix";
    const amountInCents = packageType === "master" ? 100000 : 250000; // $1000 or $2500 in cents

    const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
    
    // Call Monei API to create a payment session
    const moneiRes = await fetch("https://api.monei.com/v1/payments", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.MONEI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        amount: amountInCents,
        currency: "USD",
        orderId: `b2b_${userId}_${packageType}_${Date.now()}`,
        description: `WraGstudio API - ${packageType === "master" ? "Master" : "Mix"} Package`,
        callbackUrl: `${appUrl}/developers`,
        completeUrl: `${appUrl}/developers`,
        cancelUrl: `${appUrl}/developers`,
      }),
    });

    const moneiData = await moneiRes.json();

    if (!moneiRes.ok) {
      console.error("Monei Error:", moneiData);
      return NextResponse.json({ error: moneiData.message || "Failed to create payment" }, { status: 500 });
    }

    // Monei returns a redirectUrl for the checkout page
    const checkoutUrl = moneiData.redirectUrl || moneiData.nextAction?.redirectUrl;

    if (!checkoutUrl) {
      return NextResponse.json({ error: "Monei did not return a checkout URL" }, { status: 500 });
    }

    return NextResponse.json({ url: checkoutUrl });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
