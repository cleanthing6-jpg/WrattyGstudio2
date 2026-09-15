import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// Wakes the Render mixer so it is already booted by the time the user
// finishes uploading stems. Fire-and-forget from the client.
export async function GET() {
  const base = (process.env.MIX_API_URL || "").replace(/\/+$/, "");
  if (!base) return NextResponse.json({ ok: false, error: "MIX_API_URL not set" });
  try {
    const t0 = Date.now();
    await fetch(base + "/", { cache: "no-store", signal: AbortSignal.timeout(55000) });
    return NextResponse.json({ ok: true, ms: Date.now() - t0 });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message || "warm failed" });
  }
}
