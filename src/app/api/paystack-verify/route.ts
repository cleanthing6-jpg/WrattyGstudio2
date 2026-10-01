import { NextRequest, NextResponse } from "next/server";
import { fulfilPaystackReference } from "@/lib/paystack-fulfil";

// Browser callback = UX only. Real fulfilment is the webhook, so a closed
// tab can no longer lose a paid order.
// req.url is the container-internal origin (localhost:10000 on Render).
const appUrl = process.env.APP_URL || "https://wratty-gstudio2.onrender.com";

export async function GET(req: NextRequest) {
  const reference = req.nextUrl.searchParams.get("reference");
  if (!reference)
    return NextResponse.redirect(new URL("/dashboard?payment=failed", appUrl));

  try {
    await fulfilPaystackReference(reference);
    return NextResponse.redirect(new URL("/dashboard?payment=success", appUrl));
  } catch (err) {
    console.error("[paystack-callback] fulfil failed", err);
    return NextResponse.redirect(new URL("/dashboard?payment=failed", appUrl));
  }
}
