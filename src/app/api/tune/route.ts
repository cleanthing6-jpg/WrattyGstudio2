// src/app/api/tune/route.ts
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  // TODO: reuse your existing auth check here (app is multi-user)
  const { url, beatUrl, preset } = await req.json();
  if (typeof url !== "string" || !url.startsWith("https://")) {
    return NextResponse.json({ error: "bad url" }, { status: 400 });
  }
  const r = await fetch(process.env.MODAL_TUNE_START_URL!, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, beatUrl, preset }),
  });
  if (!r.ok) return NextResponse.json({ error: "tune start failed" }, { status: 502 });
  return NextResponse.json(await r.json());
}
