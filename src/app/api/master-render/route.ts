import { NextRequest, NextResponse } from "next/server";
import { POST as mixPOST, GET as mixGET } from "../mix/route";

export const runtime = "nodejs";
export const maxDuration = 60;

// Old RoEx mastering endpoint. Now: run the finished mix as a single stem
// through our own master chain (sum -> glue -> LUFS -> limiter).
const LOUDNESS = ["LOW", "MEDIUM", "HIGH"];

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const url = String(body?.url || "");
  if (!/^https:\/\//.test(url)) return NextResponse.json({ error: "url required" }, { status: 400 });

  const want = String(body?.loudness || "").toUpperCase();
  const loudness = LOUDNESS.includes(want) ? want : "HIGH";
  // default is the 30s preview; client sends preview:false for the full render
  const preview = body?.preview !== false;

  const headers = new Headers(req.headers);
  headers.set("content-type", "application/json");
  headers.delete("content-length");

  const inner = new NextRequest(req.url, {
    method: "POST",
    headers,
    body: JSON.stringify({ stems: [{ url, role: "mix" }], loudness, preview: preview }),
  });

  const r = await mixPOST(inner);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d?.job) {
    return NextResponse.json({ error: d?.error || "Could not start mastering" }, { status: r.status || 502 });
  }
  return NextResponse.json({ taskId: d.job });
}

export async function GET(req: NextRequest) {
  const taskId = req.nextUrl.searchParams.get("taskId") || "";
  if (!taskId) return NextResponse.json({ error: "taskId required" }, { status: 400 });

  const u = new URL(req.url);
  u.searchParams.delete("taskId");
  u.searchParams.set("id", taskId);

  const inner = new NextRequest(u, { method: "GET", headers: req.headers });
  const r = await mixGET(inner);
  const d = await r.json().catch(() => ({}));

  if (d?.status === "done" && d?.url) return NextResponse.json({ status: "done", url: d.url, previewUrl: d.url });
  if (d?.status === "failed") return NextResponse.json({ status: "failed", error: d?.error || "Master failed" });
  return NextResponse.json({ status: d?.status || "queued", previewUrl: "" });
}
