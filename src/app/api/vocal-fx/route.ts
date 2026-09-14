import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 300;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const url = String(body?.url || "");
  if (!url) return NextResponse.json({ error: "Missing url" }, { status: 400 });

  const base = process.env.FX_API_URL;
  const secret = process.env.FX_INTERNAL_SECRET;
  if (!base || !secret) {
    return NextResponse.json({ error: "FX_API_URL / FX_INTERNAL_SECRET not set" }, { status: 500 });
  }

  const r = await fetch(`${base}/api/fx`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${secret}` },
    body: JSON.stringify({
      url,
      bpm: Number(body?.bpm) || 100,
      preset: String(body?.preset || "lead"),
    }),
  });

  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.url) {
    return NextResponse.json(
      { error: data.error || `FX failed (${r.status})` },
      { status: r.status || 502 }
    );
  }
  return NextResponse.json(data);
}
