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
    const amount = packageType === "master" ? 1000 : 2500;

    const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
    
    // Using the exact headers from your screenshot
    const moneiRes = await fetch("https://api.monei.cc/api/v1/deposit/generate-payment-link", {
      method: "POST",
      headers: {
        "X-API-KEY": process.env.MONEI_API_KEY!,
        "X-API-SECRET": process.env.MONEI_SECRET_KEY!,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        amount: amount,
        currency: "USD",
        description: `WraGstudio API - ${packageType === "master" ? "Master" : "Mix"} Package`,
        redirectUrl: `${appUrl}/developers`,
        metadata: {
          orderId: `b2b_${userId}_${packageType}_${Date.now()}`
        }
      }),
    });

    const moneiData = await moneiRes.json();

    if (!moneiRes.ok) {
      console.error("Monei Gateway Error:", moneiData);
      return NextResponse.json({ error: moneiData.message || "Failed to create payment link" }, { status: 500 });
    }

    const checkoutUrl = moneiData.paymentLink || moneiData.url || moneiData.data?.paymentLink;

    if (!checkoutUrl) {
      return NextResponse.json({ error: "Monei did not return a payment link" }, { status: 500 });
    }

    return NextResponse.json({ url: checkoutUrl });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
