import { createHmac } from "crypto";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Modal files service (same one modal_files.py serves)
const FILES_BASE =
  process.env.FILES_BASE_URL || "https://wrattyg--wratty-files-web.modal.run";

// POST { url, name } -> stages that file on Modal, returns { url }
export async function POST(req: Request) {
  const key = process.env.FX_INTERNAL_SECRET || "";
  if (!key) return NextResponse.json({ error: "not configured" }, { status: 500 });

  let body: { url?: string; name?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }

  const src = String(body.url || "");
  if (!/^https?:\/\//i.test(src)) {
    return NextResponse.json({ error: "url required" }, { status: 400 });
  }

  const safe = String(body.name || "stem")
    .replace(/[^A-Za-z0-9._-]/g, "_")
    .slice(-80);

  const up = await fetch(src);
  if (!up.ok || !up.body) {
    return NextResponse.json({ error: "source " + up.status }, { status: 502 });
  }

  const exp = Math.floor(Date.now() / 1000) + 600;
  const sig = createHmac("sha256", key).update("stem-upload|" + exp).digest("hex");

  // random suffix: Modal returns 409 if the key already exists
  const dstKey =
    "stems/" + Date.now().toString(36) + "-" +
    Math.random().toString(36).slice(2, 8) + "-" + safe;

  const put = await fetch(FILES_BASE + "/u/" + dstKey, {
    method: "PUT",
    headers: {
      "x-fx-ticket": exp + "." + sig,
      "content-type": up.headers.get("content-type") || "application/octet-stream",
    },
    body: up.body,                    // streamed, never buffered in RAM
    duplex: "half",
  } as RequestInit & { duplex: "half" });

  const text = await put.text();
  if (!put.ok) {
    return NextResponse.json(
      { error: "modal " + put.status + ": " + text.slice(0, 200) },
      { status: 502 }
    );
  }

  let res: { url?: string; key?: string; bytes?: number } = {};
  try {
    res = JSON.parse(text);
  } catch {
    /* Modal always returns JSON; ignore a malformed body */
  }

  return NextResponse.json({
    url: res.url || FILES_BASE + "/f/" + dstKey,
    key: res.key || dstKey,
    bytes: res.bytes,
  });
}
