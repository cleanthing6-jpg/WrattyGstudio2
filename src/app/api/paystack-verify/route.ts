import { NextRequest, NextResponse } from "next/server";
import { setTier } from "@/lib/credits";
import { sql } from "@/lib/db";

const PRICES: Record<string, number> = {
  starter: 300000,
  pro: 700000,
  studio: 1400000,
};

async function claimReference(reference: string, userId: string, tier: string): Promise<boolean> {
  await sql`CREATE TABLE IF NOT EXISTS paystack_refs (
    reference TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  )`;
  const rows = (await sql`
    INSERT INTO paystack_refs (reference, user_id, tier)
    VALUES (${reference}, ${userId}, ${tier})
    ON CONFLICT (reference) DO NOTHING
    RETURNING reference
  `) as any[];
  return rows.length > 0;
}

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

    const first = await claimReference(reference, userId, tier);
    if (!first) {
      return NextResponse.redirect(
        new URL("/dashboard?payment=success", req.url)
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
