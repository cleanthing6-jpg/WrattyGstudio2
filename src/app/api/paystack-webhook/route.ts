import { createHmac, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { fulfilPaystackReference } from "@/lib/paystack-fulfil";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const secret = process.env.PAYSTACK_SECRET_KEY;
  if (!secret) return NextResponse.json({ error: "Not configured" }, { status: 500 });

  const raw = Buffer.from(await req.arrayBuffer());
  const sig = req.headers.get("x-paystack-signature") || "";

  if (!/^[\da-f]{128}$/i.test(sig))
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });

  const expected = createHmac("sha512", secret).update(raw).digest();
  const received = Buffer.from(sig, "hex");

  if (received.length !== expected.length || !timingSafeEqual(received, expected))
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });

  let event: any;
  try { event = JSON.parse(raw.toString("utf8")); }
  catch { return NextResponse.json({ error: "Invalid JSON" }, { status: 400 }); }

  if (event?.event !== "charge.success") return NextResponse.json({ ok: true });

  const reference = event?.data?.reference;
  if (typeof reference !== "string" || !reference)
    return NextResponse.json({ error: "Missing reference" }, { status: 400 });

  try {
    await fulfilPaystackReference(reference);
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("[paystack-webhook] fulfil failed", err);
    return NextResponse.json({ error: "Fulfilment failed" }, { status: 500 });
  }
}
