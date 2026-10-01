import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { ObjectId } from "mongodb";
import { getMongoClient } from "@/lib/mongodb";
import { sql } from "@/lib/db";

let _cols = false;
// Runs once per server process. The dashboard may be the FIRST request after a
// deploy, and the render query below filters on these columns - if they don't
// exist yet the query throws. Only flag ready once every ALTER succeeded.
async function ensureMixCols() {
  if (_cols) return;
  await sql`CREATE TABLE IF NOT EXISTS mix_jobs (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL,
    stems JSONB, loudness TEXT, preset TEXT, max_seconds INTEGER,
    credit_type TEXT, runner_job TEXT, url TEXT, result JSONB,
    created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())`;
  const stmts = [
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS artist_name TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS song_title  TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS flac_key    TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS mp3_key     TEXT`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS hidden_at   TIMESTAMP`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS max_seconds INTEGER`,
    sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS credit_type TEXT`,
  ];
  await Promise.all(stmts);
  _cols = true;
}

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

export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    try { await ensureMixCols(); } catch (e) { console.error("[mixes] columns", e); }
    await reconcile(userId);

    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    const rows = await col.find({ userId }).sort({ createdAt: -1 }).toArray();

    let jobs: any[] = [];
    let renderError: string | null = null;
    try {
      jobs = (await sql`
        SELECT id, artist_name, song_title, url, result, loudness, preset, created_at
        FROM mix_jobs
        WHERE user_id = ${userId} AND status = 'done'
          AND max_seconds IS NULL AND hidden_at IS NULL
          AND COALESCE(url, '') <> ''
        ORDER BY created_at DESC LIMIT 100`) as any[];
    } catch (e: any) {
      // Never swallow this - an empty dashboard and a broken query look the same.
      renderError = (e && e.message) || String(e);
      console.error("[mixes] render list failed", e);
    }

    const parsed = (v: any) => {
      if (typeof v === "string") { try { return JSON.parse(v); } catch { return {}; } }
      return v || {};
    };
    const tagged = new Set(rows.map((r: any) => String(r.jobId || "")).filter(Boolean));

    const renderMixes = jobs
      .filter((k: any) => !tagged.has(String(k.id)))
      .map((k: any) => {
        const f = parsed(k.result).files || {};
        const a = String(k.artist_name || "").trim();
        const t = String(k.song_title || "").trim();
        return {
          id: "job:" + k.id,
          name: a && t ? a + " - " + t : t || a || "My mix",
          url: String(k.url || ""),
          mp3: String(f.mp3 || k.url || ""),
          flac: String(f.flac || ""),
          loudness: k.loudness || "",
          preset: k.preset || "",
          createdAt: k.created_at,
        };
      });

    const body: any = {
      mixes: [...renderMixes, ...rows.map((r: any) => ({
        id: r._id.toString(), name: r.name, url: r.url,
        mp3: r.mp3 || r.url || "", flac: r.flac || "", createdAt: r.createdAt,
      }))],
    };
    if (renderError) body.renderError = renderError;
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

    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    await col.deleteOne({ _id: new ObjectId(id), userId });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}
