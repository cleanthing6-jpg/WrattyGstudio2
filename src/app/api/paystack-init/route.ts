import { auth, currentUser } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const PRICES: Record<string, number> = {
  starter: 300000,
  pro: 700000,
  studio: 1400000,
};

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

    const callbackUrl = new URL("/api/paystack-verify", req.url).toString();

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
