import { auth, currentUser } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { ALL_PAID_PLANS } from "@/lib/pricing";

// Derived from lib/pricing.ts so checkout, dashboard and bot can never drift.
// Paystack amounts are in KOBO, so naira x 100.
const PRICES: Record<string, number> = Object.fromEntries(
  ALL_PAID_PLANS.map((p) => [p.id, p.ngn * 100])
);

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();

    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { tier } = await req.json();

    if (!tier || !PRICES[tier]) {
      return NextResponse.json(
        { error: "Invalid plan selected" },
        { status: 400 }
      );
    }

    const user = await currentUser();
    const email =
      user?.primaryEmailAddress?.emailAddress ||
      user?.emailAddresses?.[0]?.emailAddress;

    if (!email) {
      return NextResponse.json(
        { error: "Your account does not have an email address" },
        { status: 400 }
      );
    }

    // req.url is the container-internal origin (http://localhost:10000 on
    // Render), so it must never be used for a public redirect.
    const appUrl = process.env.APP_URL || "https://wratty-gstudio2.onrender.com";
    const callbackUrl = new URL("/api/paystack-verify", appUrl).toString();

    const response = await fetch(
      "https://api.paystack.co/transaction/initialize",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          amount: PRICES[tier],
          currency: "NGN",
          callback_url: callbackUrl,
          metadata: {
            userId,
            tier,
          },
        }),
      }
    );

    const data = await response.json();

    if (!response.ok || !data.status || !data.data?.authorization_url) {
      return NextResponse.json(
        { error: data.message || "Unable to initialize payment" },
        { status: 502 }
      );
    }

    return NextResponse.json({
      url: data.data.authorization_url,
    });
  } catch (error) {
    console.error("Paystack initialization error:", error);

    return NextResponse.json(
      { error: "Unable to start payment" },
      { status: 500 }
    );
  }
}
