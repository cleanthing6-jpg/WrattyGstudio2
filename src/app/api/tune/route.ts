import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const { url, beatUrl, preset, key } = await req.json();

  if (typeof url !== "string" || !url.startsWith("https://")) {
    return NextResponse.json({ error: "bad url" }, { status: 400 });
  }

  const startUrl = (
    process.env.MODAL_TUNE_START_URL ||
    "https://wrattyg--wratty-autotune-start.us-east.modal.run"
  ).replace(/\/+$/, "");

  const r = await fetch(startUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, beatUrl, preset, key }),
  });

  if (!r.ok) return NextResponse.json({ error: "tune start failed" }, { status: 502 });
  return NextResponse.json(await r.json());
}
