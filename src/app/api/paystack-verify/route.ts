import { NextRequest, NextResponse } from "next/server";
import { setTier } from "@/lib/credits";
export async function GET(req: NextRequest) {
  const ref = req.nextUrl.searchParams.get("reference");
  const tier = req.nextUrl.searchParams.get("tier");
  const metadataTier = req.nextUrl.searchParams.get("metadata[userId]");
  if (!ref || !tier) return NextResponse.redirect(new URL("/dashboard", req.url));
  try {
    const res = await fetch(`https://api.paystack.co/transaction/verify/${ref}`, {
      headers: { Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}` },
    });
    const data = await res.json();
    if (data.data?.status === "success") {
      const userId = data.data.metadata?.userId;
      if (userId) await setTier(userId, tier);
    }
  } catch (e) {}
  return NextResponse.redirect(new URL("/dashboard", req.url));
}
