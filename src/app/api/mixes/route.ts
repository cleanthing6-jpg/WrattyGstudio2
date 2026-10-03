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
export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    let mongoError: string | null = null;
    let renderError: string | null = null;
    let hint = "";

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
        SELECT id, artist_name, song_title, url, result, loudness, preset, created_at,
               (hidden_at IS NOT NULL) AS deleted
        FROM mix_jobs
        WHERE user_id = ${userId} AND status = 'done'
          AND max_seconds IS NULL
          AND COALESCE(url, '') <> ''
          AND (${req.nextUrl.searchParams.get("all") === "1"}
               OR NULLIF(BTRIM(artist_name), '') IS NOT NULL
               OR NULLIF(BTRIM(song_title), '') IS NOT NULL)
        ORDER BY created_at DESC, id DESC LIMIT 1000`) as any[];
    } catch (e: any) {
      renderError = (e && e.message) || String(e);
      console.error("[mixes] render list failed", e);
    }

    // Empty list? Say WHY instead of showing a bare "no mixes". Best-effort.
    if (jobs.length === 0) {
      try {
        const st = (await sql`
          SELECT COUNT(*)::int AS total,
                 (COUNT(*) FILTER (WHERE status = 'done'))::int AS done,
                 (COUNT(*) FILTER (WHERE status = 'done' AND hidden_at IS NOT NULL))::int AS hidden,
                 (COUNT(*) FILTER (WHERE status = 'done' AND max_seconds IS NOT NULL))::int AS previews,
                 (COUNT(*) FILTER (WHERE status = 'done' AND COALESCE(url,'') = ''))::int AS no_url,
                 (COUNT(*) FILTER (WHERE status IN ('queued','running')))::int AS pending,
                 (COUNT(*) FILTER (WHERE status = 'failed'))::int AS failed
          FROM mix_jobs WHERE user_id = ${userId}`) as any[];
        const g = (await sql`SELECT COUNT(*)::int AS n FROM mix_jobs`) as any[];
        const r: any = st[0] || {};
        if (Number(r.total || 0) === 0 && Number(g[0]?.n || 0) > 0) {
          hint = "your renders are under a different account id - sign in with the account that made them";
        } else if (Number(r.hidden || 0) > 0) {
          hint = "you have " + r.hidden + " deleted render(s) - press Restore";
        } else if (Number(r.no_url || 0) > 0) {
          hint = "a render finished but saved no file url";
        } else if (Number(r.pending || 0) > 0) {
          hint = "a render is still running - refresh in a minute";
        } else if (Number(r.failed || 0) > 0) {
          hint = r.failed + " render(s) failed - check the Modal logs";
        } else if (Number(r.previews || 0) > 0) {
          hint = "only previews so far - run a full render";
        } else {
          hint = "no renders on this account yet";
        }
      } catch (e: any) {
        console.error("[mixes] stats failed", e);
      }
    }

    // The dashboard is a library of FINISHED MASTERS - one card per song.
    // One song can leave two jobs (a mix pass and a master pass) and every
    // retry leaves another, so collapse them: masters only, newest first,
    // keyed by artist|title. Unnamed rows key on their own id so they never
    // merge with each other. ?all=1 shows everything, mix passes included.
    const all = req.nextUrl.searchParams.get("all") === "1";
    const seen = new Set<string>();
    const kept = jobs.filter((r: any) => {
      let res: any = r.result;
      if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
      const mode = String((res && res.mode) || "").toLowerCase();
      // named renders always show; dedupe below keeps the newest pass per song
      const a = String(r.artist_name || "").trim().toLowerCase();
      const t = String(r.song_title || "").trim().toLowerCase();
      if (!all && !(a || t)) return false;   // pre-naming rows -> ?all=1
      const key = a || t ? a + "|" + t : "id:" + r.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    const rendered = kept.map((r: any) => {
      let res: any = r.result;
      if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
      const files = (res && res.files) || {};
      const mp3 = String(files.mp3 || "");
      const flac = String(files.flac || "");
      const a = String(r.artist_name || "").trim();
      const t = String(r.song_title || "").trim();
      const when = r.created_at
        ? new Date(r.created_at).toISOString().slice(0, 16).replace("T", " ")
        : "";
      const name = a && t
        ? a + " - " + t
        : (t || a) || ("Untitled master" + (when ? " - " + when : ""));
      return { id: "job:" + r.id, name, url: mp3 || flac || String(r.url || ""), mp3, flac, deleted: !!r.deleted, createdAt: r.created_at };
    });

    const mixes = [
      ...rendered,
      ...legacy.map((r: any) => ({
        id: r._id.toString(), name: r.name, url: r.url,
        mp3: r.mp3 || r.url || "", flac: r.flac || "", createdAt: r.createdAt,
      })),
    ];

    const body: any = { mixes, jobs: jobs.length, shown: kept.length };
    if (hint) body.hint = hint;
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
      const restore = req.nextUrl.searchParams.get("restore") === "1";
      await sql`UPDATE mix_jobs SET hidden_at = CASE WHEN ${restore} THEN NULL ELSE NOW() END
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
