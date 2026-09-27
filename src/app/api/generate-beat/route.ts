import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BEAT_API = process.env.BEAT_API_URL || "";
const SECRET = process.env.FX_INTERNAL_SECRET || "";

// Starts a beat on the Modal job API and returns immediately.
// Rendering happens on the GPU; poll /api/beat-status for the result.
export async function POST(req: NextRequest) {
  try {
    if (!BEAT_API || !SECRET) {
      return NextResponse.json(
        { error: "beat engine not configured" },
        { status: 500 },
      );
    }

    const body = await req.json().catch(() => ({} as any));
    const prompt = String(body?.prompt || "").trim();

    if (!prompt) {
      return NextResponse.json({ error: "prompt is required" }, { status: 400 });
    }

    const duration = Number(body?.duration) || 45;
    // fresh seed per call, so "generate again" actually makes a new beat
    const seed = Number(body?.seed) || Math.floor(Math.random() * 1e9);

    const r = await fetch(`${BEAT_API}/`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${SECRET}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ prompt, duration, seed }),
      cache: "no-store",
    });

    const data = await r.json().catch(() => ({} as any));

    if (!r.ok || !data?.job) {
      return NextResponse.json(
        { error: data?.error || "Failed to start beat generation" },
        { status: r.status || 500 },
      );
    }

    return NextResponse.json({ job: data.job }, { status: 202 });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Request failed" },
      { status: 500 },
    );
  }
}
