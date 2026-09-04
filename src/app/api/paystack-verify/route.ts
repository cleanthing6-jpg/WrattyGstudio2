import { NextRequest, NextResponse } from "next/server";
import { setTier } from "@/lib/credits";

const PRICES: Record<string, number> = {
  starter: 300000,
  pro: 700000,
  studio: 1400000,
};

export async function GET(req: NextRequest) {
  const reference = req.nextUrl.searchParams.get("reference");

  if (!reference) {
    return NextResponse.redirect(
      new URL("/dashboard?payment=failed", req.url)
    );
  }

  try {
    const response = await fetch(
      `https://api.paystack.co/transaction/verify/${encodeURIComponent(reference)}`,
      {
        headers: {
          Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}`,
        },
      }
    );

    const data = await response.json();
    const transaction = data.data;

    if (!response.ok || transaction?.status !== "success") {
      return NextResponse.redirect(
        new URL("/dashboard?payment=failed", req.url)
      );
    }

    const userId = transaction.metadata?.userId;
    const tier = transaction.metadata?.tier;
    const expectedAmount = PRICES[tier];

    if (
      typeof userId !== "string" ||
      typeof tier !== "string" ||
      !expectedAmount ||
      transaction.amount !== expectedAmount ||
      transaction.currency !== "NGN"
    ) {
      return NextResponse.redirect(
        new URL("/dashboard?payment=failed", req.url)
      );
    }

    await setTier(userId, tier);

    return NextResponse.redirect(
      new URL("/dashboard?payment=success", req.url)
    );
  } catch {
    return NextResponse.redirect(
      new URL("/dashboard?payment=failed", req.url)
    );
  }
}
