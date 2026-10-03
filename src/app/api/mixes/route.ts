import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { ObjectId } from "mongodb";
import { getMongoClient } from "@/lib/mongodb";
import { sql } from "@/lib/db";
// Runs once per server process. The dashboard may be the FIRST request after a
// deploy, and the render query below filters on these columns - if they don't
// exist yet the query throws. Only flag ready once every ALTER succeeded.

// A job can finish in Modal while the browser has already navigated away - then
// nothing ever flips the row to 'done' and it never reaches the dashboard. Ask
// Modal directly for anything stuck longer than 90s. Best-effort: never throws.
async function reconcile(userId: string) {
  try {
    const rows = (await sql`
      SELECT id, runner_job FROM mix_jobs
      WHERE user_id = ${userId} AND status IN ('queued','running')
        AND COALESCE(runner_job,'') <> ''
        AND created_at < NOW() - INTERVAL '90 seconds'
      ORDER BY created_at DESC LIMIT 5`) as any[];
    if (!rows.length) return;
    const base = (process.env.MIX_APP_URL || "https://wrattyg--wratty-mix-api.modal.run").replace(/\/+$/, "");
    const secret = process.env.FX_INTERNAL_SECRET || "";
    for (const r of rows) {
      try {
        const res = await fetch(base + "/?id=" + encodeURIComponent(String(r.runner_job)), {
          cache: "no-store",
          headers: secret ? { Authorization: "Bearer " + secret } : undefined,
          signal: AbortSignal.timeout(8000),
        });
        if (!res.ok) continue;
        const d: any = await res.json().catch(() => null);
        if (!d || d.status !== "done") continue;
        const files = (d.result && d.result.files) || {};
        const mp3 = String(files.mp3 || "");
        const flac = String(files.flac || "");
        const url = String(d.url || mp3 || flac || "");
        if (!url) continue;
        await sql`
          UPDATE mix_jobs SET status='done', url=${url},
            flac_key=${flac || null}, mp3_key=${mp3 || null},
            result=${JSON.stringify(d.result || {})}::jsonb, updated_at=NOW()
          WHERE id=${r.id} AND status <> 'done'`;
      } catch (e) {
        console.error("[mixes] reconcile failed", r.id, e);
      }
    }
  } catch (e) {
    console.error("[mixes] reconcile query failed", e);
  }
}
let _cols = false;
async function ensureMixCols() {
  if (_cols) return;
  await sql`CREATE TABLE IF NOT EXISTS mix_jobs (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL,
    stems JSONB, loudness TEXT, preset TEXT, max_seconds INTEGER,
    credit_type TEXT, runner_job TEXT, url TEXT, result JSONB,
    created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())`;
  await Promise.all([
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS artist_name TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS song_title  TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS flac_key    TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS mp3_key     TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS hidden_at   TIMESTAMP`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS max_seconds INTEGER`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS credit_type TEXT`,
  ]);
  _cols = true;
}

// Dashboard lists TWO sources: finished engine renders (Postgres mix_jobs,
// done, full renders only) and the legacy Mongo list (Beat-Lock saves).
// Either source failing must not blank the other.
export async function GET() {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    let mongoError: string | null = null;
    let renderError: string | null = null;

    let legacy: any[] = [];
    try {
      const client = await getMongoClient();
      legacy = await client.db("wrattyg").collection("mixes")
        .find({ userId }).sort({ createdAt: -1 }).toArray();
    } catch (e: any) {
      mongoError = (e && e.message) || String(e);
      console.error("[mixes] mongo failed", e);
    }

    let jobs: any[] = [];
    try {
      await ensureMixCols();
      jobs = (await sql`
        SELECT id, artist_name, song_title, url, result, loudness, preset, created_at
        FROM mix_jobs
        WHERE user_id = ${userId} AND status = 'done'
          AND max_seconds IS NULL AND hidden_at IS NULL
          AND COALESCE(url, '') <> ''
        ORDER BY created_at DESC LIMIT 100`) as any[];
    } catch (e: any) {
      renderError = (e && e.message) || String(e);
      console.error("[mixes] render list failed", e);
    }

    const rendered = jobs.map((r: any) => {
      let res: any = r.result;
      if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
      const files = (res && res.files) || {};
      const mp3 = String(files.mp3 || "");
      const flac = String(files.flac || "");
      const a = String(r.artist_name || "").trim();
      const t = String(r.song_title || "").trim();
      const name = a && t ? a + " - " + t : t || a || "My mix";
      return { id: "job:" + r.id, name, url: mp3 || flac || String(r.url || ""), mp3, flac, createdAt: r.created_at };
    });

    const mixes = [
      ...rendered,
      ...legacy.map((r: any) => ({
        id: r._id.toString(), name: r.name, url: r.url,
        mp3: r.mp3 || r.url || "", flac: r.flac || "", createdAt: r.createdAt,
      })),
    ];

    const body: any = { mixes };
    if (renderError) body.renderError = renderError;
    if (mongoError) body.mongoError = mongoError;
    return NextResponse.json(body);
  } catch (e: any) {
    console.error("[mixes] GET failed", e);
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const body = await req.json();
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 120) : "";
    const url = typeof body.url === "string" ? body.url.trim() : "";
    if (!name || !url) return NextResponse.json({ error: "Name and URL required" }, { status: 400 });
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    const res = await col.insertOne({ userId, name, url, createdAt: new Date() });
    return NextResponse.json({ id: res.insertedId.toString() });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const id = req.nextUrl.searchParams.get("id");
    if (!id) return NextResponse.json({ error: "Missing id" }, { status: 400 });

    // Engine renders are listed from Postgres, so "dismiss" = hide, never
    // delete. The rendered file stays available.
    if (id.startsWith("job:")) {
      await sql`UPDATE mix_jobs SET hidden_at = NOW()
                WHERE id = ${id.slice(4)} AND user_id = ${userId}`;
      return NextResponse.json({ ok: true });
    }

    if (id.startsWith("job:")) {
      await ensureMixCols();
      await sql`UPDATE mix_jobs SET hidden_at = NOW()
                WHERE id = ${id.slice(4)} AND user_id = ${userId}`;
      return NextResponse.json({ ok: true });
    }
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    await col.deleteOne({ _id: new ObjectId(id), userId });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}
