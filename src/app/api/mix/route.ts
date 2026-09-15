import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const runtime = "nodejs";
export const maxDuration = 60;

const MIX = (process.env.MIX_API_URL || "https://wratty-mix.onrender.com").replace(/\/+$/, "");
const SECRET = process.env.FX_INTERNAL_SECRET || "";
const MAX_ACTIVE = 2;

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

  await ensureTable();

  const active = (await sql`SELECT COUNT(*)::int AS n FROM mix_jobs
    WHERE user_id = ${userId} AND status IN ('queued','running')`) as any[];
  if (Number(active[0]?.n || 0) >= MAX_ACTIVE)
    return NextResponse.json({ error: "You already have mixes running - wait for them to finish" }, { status: 429 });

  const id = crypto.randomUUID();
  await sql`INSERT INTO mix_jobs (id, user_id, status, stems, loudness, preset)
    VALUES (${id}, ${userId}, 'queued', ${JSON.stringify(stems)}::jsonb, ${loudness}, ${preset})`;

  const r = await mixer("/", { method: "POST", body: JSON.stringify({ stems, loudness, preset }) }, 3, [502, 503]);
  if (!r.ok || !(r.data && r.data.job)) {
    await sql`UPDATE mix_jobs SET status='failed', error=${String(r.error || "mixer did not start")},
              updated_at=NOW() WHERE id=${id}`;
    return NextResponse.json({ error: r.error || "mixer did not return a job", id }, { status: r.status || 502 });
  }

  await sql`UPDATE mix_jobs SET status='running', runner_job=${String(r.data.job)},
            updated_at=NOW() WHERE id=${id}`;
  return NextResponse.json({ job: id, status: "running" }, { status: 202 });
}

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const id = req.nextUrl.searchParams.get("id") || "";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  const rows = (await sql`SELECT * FROM mix_jobs WHERE id=${id} AND user_id=${userId}`) as any[];
  const row = rows[0];
  if (!row) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (row.status === "done" || row.status === "failed") return NextResponse.json(row);

  const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 4, [502, 503, 504]);
  const d = r.ok ? r.data : null;

  if (d && d.status === "done" && d.url) {
    await sql`UPDATE mix_jobs SET status='done', url=${d.url},
              result=${JSON.stringify(d.result || {})}::jsonb, updated_at=NOW() WHERE id=${id}`;
  } else if (d && d.status === "failed") {
    await sql`UPDATE mix_jobs SET status='failed', error=${String(d.error || "mix failed")},
              updated_at=NOW() WHERE id=${id}`;
  } else if (d && d.status === "none") {
    await sql`UPDATE mix_jobs SET status='failed',
              error='Mixer restarted before finishing - please try again', updated_at=NOW() WHERE id=${id}`;
  }

  const after = (await sql`SELECT * FROM mix_jobs WHERE id=${id}`) as any[];
  return NextResponse.json(after[0] || row);
}
