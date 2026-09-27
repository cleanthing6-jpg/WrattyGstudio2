import { createHmac } from "crypto";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Tiny ticket request - no file data, so nowhere near the 4.5 MB function
// body limit. The browser then PUTs the stem straight to Modal.
export async function POST() {
  const key = process.env.FX_INTERNAL_SECRET || "";
  if (!key) {
    return NextResponse.json({ error: "not configured" }, { status: 500 });
  }

  const exp = Math.floor(Date.now() / 1000) + 600; // 10 minutes
  const sig = createHmac("sha256", key)
    .update("stem-upload|" + exp)
    .digest("hex");

  return NextResponse.json({
    ticket: exp + "." + sig,
    uploadUrl: "https://wrattyg--wratty-files-web.modal.run",
    expires: exp,
  });
}
