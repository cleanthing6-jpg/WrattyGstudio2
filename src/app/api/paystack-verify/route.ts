import { NextRequest, NextResponse } from "next/server";
import { fulfilPaystackReference } from "@/lib/paystack-fulfil";

// Browser callback = UX only. Real fulfilment is the webhook, so a closed
// tab can no longer lose a paid order.
export async function GET(req: NextRequest) {
  const reference = req.nextUrl.searchParams.get("reference");
  if (!reference)
    return NextResponse.redirect(new URL("/dashboard?payment=failed", req.url));

  try {
    await fulfilPaystackReference(reference);
    return NextResponse.redirect(new URL("/dashboard?payment=success", req.url));
  } catch (err) {
    console.error("[paystack-callback] fulfil failed", err);
    return NextResponse.redirect(new URL("/dashboard?payment=failed", req.url));
  }
}
