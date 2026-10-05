import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { sql } from "@/lib/db";
import { POST as mixPOST, GET as mixGET } from "../mix/route";

export const runtime = "nodejs";
export const maxDuration = 60;

// Old RoEx mastering endpoint. Now: run the finished mix as a single stem
// through our own master chain (sum -> glue -> LUFS -> limiter).
const LOUDNESS = ["LOW", "MEDIUM", "HIGH"];

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  let url = String(body?.url || "");

  // The browser only ever holds same-origin /api/download?... URLs, which the
  // Modal worker cannot fetch (no Clerk session, and it requires https).
  // Resolve the real stored source from the job id instead.
  let jobId = String(body?.jobId || "");
  if (!/^https:\/\//.test(url)) {
    try {
      const parsed = new URL(url, req.url);
      const m = (parsed.searchParams.get("id") || "").match(/^job:(.+)$/);
      if (m) jobId = m[1];
    } catch {}
  }
  if (!/^https:\/\//.test(url) && jobId) {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const rows = (await sql`
      SELECT url, mp3_key, flac_key, result FROM mix_jobs
      WHERE id = ${jobId} AND user_id = ${userId}`) as any[];
    const row = rows[0];
    if (!row) return NextResponse.json({ error: "job not found" }, { status: 404 });
    let res: any = row.result;
    if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
    const files = (res && res.files) || {};
    url = String(row.flac_key || row.mp3_key || files.mp3 || files.flac || row.url || "");
  }
  if (!/^https:\/\//.test(url)) return NextResponse.json({ error: "url or jobId required" }, { status: 400 });

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
    body: JSON.stringify({
      stems: [{ url, role: "mix" }],
      loudness,
      preview: preview,
      artist: String(body?.artist || ""),
      title: String(body?.title || ""),
      mode: "master",
    }),
  });

  const r = await mixPOST(inner);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d?.job) {
    return NextResponse.json({ error: d?.error || "Could not start mastering" }, { status: r.status || 502 });
  }

  // The mix job (mode two_track, ~-14 LUFS) is an INTERMEDIATE mix, never a
  // deliverable. It used to reach the dashboard the moment mixing finished, so
  // anyone who refreshed while mastering still ran downloaded an unmastered,
  // 4 LU quiet file. Now that a master exists for it, retire the intermediate
  // so it can never be served as a finished render again. Best-effort: a
  // failure here must not break mastering.
  if (jobId) {
    try {
      const { userId: uid } = await auth();
      if (uid) {
        await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMP`;
        await sql`UPDATE mix_jobs SET superseded_at = NOW()
                  WHERE id = ${jobId} AND user_id = ${uid}`;
      }
    } catch (e) {
      console.error("[master-render] could not retire intermediate mix", e);
    }
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

  if (d?.status === "done" && d?.url) {
    return NextResponse.json({
      status: "done",
      url: d.url,
      previewUrl: d.url,
      dashboardSaved: d.dashboardSaved === true,
      dashboardName: String(d.dashboardName || ""),
    });
  }
  if (d?.status === "failed") return NextResponse.json({ status: "failed", error: d?.error || "Master failed" });
  return NextResponse.json({ status: d?.status || "queued", previewUrl: "" });
}
