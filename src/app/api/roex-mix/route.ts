import { NextRequest, NextResponse } from "next/server";
import { POST as mixPOST, GET as mixGET } from "../mix/route";

export const runtime = "nodejs";
export const maxDuration = 60;

// The client still calls the old RoEx contract:
//   POST { stems }        -> { taskId }
//   GET  ?taskId=<id>     -> { status: "preview", url }
// It is now served by our OWN mixer as a 30-second preview.
const LOUDNESS = ["LOW", "MEDIUM", "HIGH"];

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const stems = Array.isArray(body?.stems) ? body.stems : [];
  if (!stems.length) return NextResponse.json({ error: "stems[] required" }, { status: 400 });

  const want = String(body?.loudness || "").toUpperCase();
  const loudness = LOUDNESS.includes(want) ? want : "HIGH";

  const headers = new Headers(req.headers);
  headers.set("content-type", "application/json");
  headers.delete("content-length");

  const inner = new NextRequest(req.url, {
    method: "POST",
    headers,
    body: JSON.stringify({ stems, loudness, preview: true }),
  });

  const r = await mixPOST(inner);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d?.job) {
    return NextResponse.json({ error: d?.error || "Could not start the preview" }, { status: r.status || 502 });
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

  if (d?.status === "done" && d?.url) return NextResponse.json({ status: "preview", url: d.url });
  if (d?.status === "failed") return NextResponse.json({ status: "failed", error: d?.error || "Preview failed" });
  return NextResponse.json({ status: d?.status || "queued", url: "", position: d?.position || 0 });
}
