import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const runtime = "nodejs";
export const maxDuration = 60;

const MIX = (process.env.MIX_API_URL || "https://wratty-mix.onrender.com").replace(/\/+$/, "");
const SECRET = process.env.FX_INTERNAL_SECRET || "";

// Free Render = one 512MB instance. Only ONE mix may run at a time.
const MAX_RUNNING = 1;
// Each user may hold at most one mix (queued or running).
const MAX_PER_USER = 1;

async function ensureTable() {
  await sql`CREATE TABLE IF NOT EXISTS mix_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    stems JSONB NOT NULL,
    loudness TEXT NOT NULL DEFAULT 'MEDIUM',
    preset TEXT,
    runner_job TEXT,
    url TEXT,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
  )`;
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS max_seconds INTEGER`;
}

async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[]) {
  let last = "unknown";
  for (let k = 0; k < tries; k++) {
    try {
      const r = await fetch(MIX + path, {
        ...init,
        cache: "no-store",
        headers: {
          Authorization: "Bearer " + SECRET,
          "Content-Type": "application/json",
          ...(init.headers || {}),
        },
        signal: AbortSignal.timeout(120000),
      });
      const text = await r.text();
      let data: any = null;
      try { data = JSON.parse(text); } catch { data = null; }
      if (r.ok) return { ok: true, status: r.status, data, error: "" };
      last = (data && (data.error || data.message)) || "HTTP " + r.status;
      if (!retryCodes.includes(r.status)) return { ok: false, status: r.status, data, error: last };
    } catch (e: any) {
      last = e?.name === "TimeoutError" ? "mixer timed out" : (e?.message || "network error");
    }
    if (k < tries - 1) await new Promise((r) => setTimeout(r, [5000, 10000, 20000, 30000, 60000][Math.min(k, 4)]));
  }
  return { ok: false, status: 0, data: null, error: "mixer unreachable: " + last };
}

// A job left 'running' too long means Render died mid-mix.
async function reapStale() {
  await sql`UPDATE mix_jobs
    SET status='failed', error='Mixer restarted before finishing - please try again', updated_at=NOW()
    WHERE status='running' AND updated_at < NOW() - INTERVAL '12 minutes'`;
}

// Start the oldest queued job, but only if nothing is running.
// Single atomic statement, so two callers cannot start two jobs.
async function pump(): Promise<void> {
  const started = (await sql`
    UPDATE mix_jobs SET status='running', updated_at=NOW()
    WHERE id = (SELECT id FROM mix_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1)
      AND (SELECT COUNT(*) FROM mix_jobs WHERE status='running') < ${MAX_RUNNING}
    RETURNING *
  `) as any[];
  const job = started[0];
  if (!job) return;

  let stems: any = job.stems;
  if (typeof stems === "string") { try { stems = JSON.parse(stems); } catch { stems = []; } }

  const r = await mixer("/", {
    method: "POST",
    body: JSON.stringify({ stems, loudness: job.loudness, preset: job.preset, maxSeconds: job.max_seconds || 0 }),
  }, 3, [429, 502, 503]);

  if (!r.ok || !(r.data && r.data.job)) {
    await sql`UPDATE mix_jobs SET status='failed',
              error=${String(r.error || "mixer did not start")}, updated_at=NOW() WHERE id=${job.id}`;
    return;
  }
  await sql`UPDATE mix_jobs SET runner_job=${String(r.data.job)}, updated_at=NOW() WHERE id=${job.id}`;
}

async function positionOf(id: string): Promise<number> {
  const rows = (await sql`SELECT COUNT(*)::int AS n FROM mix_jobs
    WHERE status IN ('queued','running')
      AND created_at < (SELECT created_at FROM mix_jobs WHERE id = ${id})`) as any[];
  return Number(rows[0]?.n || 0) + 1;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!SECRET) return NextResponse.json({ error: "Mixer not configured" }, { status: 500 });

  let body: any = {};
  try { body = await req.json(); } catch {}
  const stems = (Array.isArray(body?.stems) ? body.stems : [])
    .map((s: any) => ({ url: String(s?.url || ""), role: String(s?.role || s?.name || "stem") }))
    .filter((s: any) => /^https:\/\//.test(s.url));
  if (!stems.length) return NextResponse.json({ error: "stems[] with https urls required" }, { status: 400 });

  const loudness = String(body?.loudness || "MEDIUM").toUpperCase();
  const preset = body?.preset ? String(body.preset) : null;
  const maxSeconds = body?.preview === true ? 30 : null;

  await ensureTable();
  await reapStale();

  const mine = (await sql`SELECT COUNT(*)::int AS n FROM mix_jobs
    WHERE user_id = ${userId} AND status IN ('queued','running')`) as any[];
  if (Number(mine[0]?.n || 0) >= MAX_PER_USER)
    return NextResponse.json({ error: "You already have a mix in the queue - wait for it to finish" }, { status: 429 });

  const id = crypto.randomUUID();
  await sql`INSERT INTO mix_jobs (id, user_id, status, stems, loudness, preset, max_seconds)
    VALUES (${id}, ${userId}, 'queued', ${JSON.stringify(stems)}::jsonb, ${loudness}, ${preset}, ${maxSeconds})`;

  const rows = (await sql`SELECT * FROM mix_jobs WHERE id=${id}`) as any[];
  const row = rows[0] || {};
  const position = row.status === "running" ? 0 : await positionOf(id);
  return NextResponse.json({ job: id, status: row.status, position }, { status: 202 });
}

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const id = req.nextUrl.searchParams.get("id") || "";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  await reapStale();
  await pump();

  const rows = (await sql`SELECT * FROM mix_jobs WHERE id=${id} AND user_id=${userId}`) as any[];
  let row = rows[0];
  if (!row) return NextResponse.json({ error: "not found" }, { status: 404 });

  if (row.status === "queued") {
    return NextResponse.json({ ...row, position: await positionOf(id) });
  }
  if (row.status === "done" || row.status === "failed") {
    return NextResponse.json({ ...row, position: 0 });
  }

  const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 4, [502, 503, 504]);
  const d = r.ok ? r.data : null;

  if (d && d.status === "done" && d.url) {
    await sql`UPDATE mix_jobs SET status='done', url=${d.url},
              result=${JSON.stringify(d.result || {})}::jsonb, updated_at=NOW() WHERE id=${id}`;
  } else if (d && d.status === "failed") {
    await sql`UPDATE mix_jobs SET status='failed',
              error=${String(d.error || "mix failed")}, updated_at=NOW() WHERE id=${id}`;
  } else if (d && d.status === "none") {
    await sql`UPDATE mix_jobs SET status='failed',
              error='Mixer restarted before finishing - please try again', updated_at=NOW() WHERE id=${id}`;
  }

  await pump();

  const after = (await sql`SELECT * FROM mix_jobs WHERE id=${id}`) as any[];
  return NextResponse.json({ ...(after[0] || row), position: 0 });
}
