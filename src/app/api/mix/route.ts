import { auth, clerkClient } from "@clerk/nextjs/server";
import { sendRenderEmail } from "@/lib/mail";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { getUser, consumeCredit, refundCredit } from "@/lib/credits";

export const runtime = "nodejs";
export const maxDuration = 60;

const RAW_MIX = process.env.MIX_API_URL || "";
// Ignore a misconfigured value (e.g. the secret pasted into the URL field)
// and fall back to the Modal engine instead of the old Render host.
const MIX = (/^https?:\/\//.test(RAW_MIX)
  ? RAW_MIX
  : "https://wrattyg--wratty-mix-api.modal.run"
).replace(/\/+$/, "");
const SECRET = process.env.FX_INTERNAL_SECRET || "";

// Free Render = one 512MB instance. Only ONE mix may run at a time.
const MAX_RUNNING = 1;
// Each user may hold at most one mix (queued or running).

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
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS credit_type TEXT`;
}

async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[], ms = 45000) {
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
        signal: AbortSignal.timeout(ms),
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


// Fail a job AND give the credit back in ONE statement. The status guard
// means exactly one caller can win, so a credit is never refunded twice.
async function failJob(id: string, error: string) {
  await sql`
    WITH f AS (
      UPDATE mix_jobs SET status='failed', error=${error}, updated_at=NOW()
      WHERE id=${id} AND status IN ('queued','running')
      RETURNING user_id, credit_type
    ), r AS (
      UPDATE users u SET
        mixes_used   = CASE WHEN sub.ct = 'mix'    THEN GREATEST(0, u.mixes_used - 1)   ELSE u.mixes_used   END,
        masters_used = CASE WHEN sub.ct = 'master' THEN GREATEST(0, u.masters_used - 1) ELSE u.masters_used END
      FROM (SELECT user_id, max(credit_type) AS ct FROM f GROUP BY user_id) sub
      WHERE u.id = sub.user_id
      RETURNING u.id
    )
    SELECT 1
  `;
}

async function reapStale() {
  // Every statement below fails jobs AND refunds any credit they spent.
  await sql`
    WITH f AS (
      UPDATE mix_jobs SET status='failed', error='Mixer restarted before finishing - please try again', updated_at=NOW()
      WHERE status='running' AND (updated_at < NOW() - INTERVAL '8 minutes' OR created_at < NOW() - INTERVAL '20 minutes')
      RETURNING user_id, credit_type
    ), r AS (
      UPDATE users u SET
        mixes_used   = GREATEST(0, u.mixes_used   - sub.m),
        masters_used = GREATEST(0, u.masters_used - sub.mm)
      FROM (SELECT user_id, count(*) FILTER (WHERE credit_type='mix') AS m,
                   count(*) FILTER (WHERE credit_type='master') AS mm
            FROM f GROUP BY user_id) sub
      WHERE u.id = sub.user_id RETURNING u.id
    ) SELECT 1
  `;
  await sql`
    WITH f AS (
      UPDATE mix_jobs SET status='failed', error='Mixer queue expired - please try again', updated_at=NOW()
      WHERE status='queued' AND created_at < NOW() - INTERVAL '3 minutes'
      RETURNING user_id, credit_type
    ), r AS (
      UPDATE users u SET
        mixes_used   = GREATEST(0, u.mixes_used   - sub.m),
        masters_used = GREATEST(0, u.masters_used - sub.mm)
      FROM (SELECT user_id, count(*) FILTER (WHERE credit_type='mix') AS m,
                   count(*) FILTER (WHERE credit_type='master') AS mm
            FROM f GROUP BY user_id) sub
      WHERE u.id = sub.user_id RETURNING u.id
    ) SELECT 1
  `;
  await sql`
    WITH f AS (
      UPDATE mix_jobs SET status='failed', error='Render never started - please try again', updated_at=NOW()
      WHERE status='running' AND runner_job IS NULL AND updated_at < NOW() - INTERVAL '10 minutes'
      RETURNING user_id, credit_type
    ), r AS (
      UPDATE users u SET
        mixes_used   = GREATEST(0, u.mixes_used   - sub.m),
        masters_used = GREATEST(0, u.masters_used - sub.mm)
      FROM (SELECT user_id, count(*) FILTER (WHERE credit_type='mix') AS m,
                   count(*) FILTER (WHERE credit_type='master') AS mm
            FROM f GROUP BY user_id) sub
      WHERE u.id = sub.user_id RETURNING u.id
    ) SELECT 1
  `;
}

// Start the oldest queued job, but only if nothing is running.
// Single atomic statement, so two callers cannot start two jobs.
async function pump(depth = 0): Promise<void> {
  const started = (await sql`
    UPDATE mix_jobs SET status='running', updated_at=NOW()
    WHERE id = (SELECT id FROM mix_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1)
      AND (SELECT COUNT(*) FROM mix_jobs
        WHERE status='running' AND updated_at > NOW() - INTERVAL '8 minutes') < ${MAX_RUNNING}
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
    await failJob(job.id, String(r.error || "mixer did not start"));
    if (depth < 5) await pump(depth + 1);   // never stall the queue
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
  const preset = body?.preset ? String(body.preset) : "afrobeats";
  const wantsPreview = body?.preview === true;
  const mode = body?.mode === "master" ? "master" : "mix";
  let creditType: string | null = null;
  const user = await getUser(userId);
  const tier = String(user.tier || "free");
  const ownerId = (process.env.OWNER_USER_ID || "user_3JwUmxdbT5FMshejHI7swJNHs9t").trim();
  const isOwner = !!ownerId && userId === ownerId;

  let maxSeconds: number | null;
  if (wantsPreview) {
    maxSeconds = 30;   // a preview is ALWAYS 30s - owner included
  } else if (isOwner) {
    maxSeconds = null; // owner full render: full length, no charge
  } else if (tier === "free") {
    if (mode === "master") {
      return NextResponse.json(
        { error: "Buy a Master pack to download the full master" },
        { status: 403 }
      );
    }
    maxSeconds = 30;
  } else if (mode === "master") {
    const ok = await consumeCredit(userId, "master");
    if (!ok) {
      return NextResponse.json(
        { error: "No mastering credits remaining - buy a Master pack" },
        { status: 403 }
      );
    }
    creditType = "master";
    maxSeconds = null;
  } else {
    const ok = await consumeCredit(userId, "mix");
    if (!ok) {
      return NextResponse.json(
        { error: "No full-mix credits remaining" },
        { status: 403 }
      );
    }
    creditType = "mix";
    maxSeconds = null;
  }

  console.log("[mix-debug]", { ownerConfigured: !!ownerId, isOwner, wantsPreview, tier, maxSeconds });
  await ensureTable();
    if (!isOwner && (wantsPreview || tier === "free")) {
      const recent = (await sql`SELECT COUNT(*)::int AS n FROM mix_jobs
        WHERE user_id = ${userId} AND created_at > NOW() - INTERVAL '24 hours'`) as any[];
      if (Number(recent[0]?.n || 0) >= 10) {
        return NextResponse.json({ error: "Daily preview limit reached - upgrade for full mixes" }, { status: 429 });
      }
    }
  await reapStale();
  // Pressing Mix again means the previous run was abandoned - drop it so it
  // can never block the new one and can never pile up.
  await sql`
    WITH f AS (
      UPDATE mix_jobs SET status='failed', error='Superseded by your newer request', updated_at=NOW()
      WHERE user_id = ${userId} AND status IN ('queued','running')
        AND created_at < NOW() - INTERVAL '3 minutes'
      RETURNING user_id, credit_type
    ), r AS (
      UPDATE users u SET
        mixes_used   = GREATEST(0, u.mixes_used   - sub.m),
        masters_used = GREATEST(0, u.masters_used - sub.mm)
      FROM (SELECT user_id, count(*) FILTER (WHERE credit_type='mix') AS m,
                   count(*) FILTER (WHERE credit_type='master') AS mm
            FROM f GROUP BY user_id) sub
      WHERE u.id = sub.user_id RETURNING u.id
    ) SELECT 1
  `;

  // No per-user rejection. A new request supersedes your own older
  // job instead of blocking you; the shared queue still protects the engine.

  const id = crypto.randomUUID();
  try {
    await sql`INSERT INTO mix_jobs (id, user_id, status, stems, loudness, preset, max_seconds, credit_type)
      VALUES (${id}, ${userId}, 'queued', ${JSON.stringify(stems)}::jsonb, ${loudness}, ${preset}, ${maxSeconds}, ${creditType})`;
  } catch (e) {
    // The credit was already spent but no job exists to refund it - give it back now.
    if (creditType) await refundCredit(userId, creditType as any);
    throw e;
  }

  const rows = (await sql`SELECT * FROM mix_jobs WHERE id=${id}`) as any[];
  const row = rows[0] || {};
  const position = row.status === "running" ? 0 : await positionOf(id);
  return NextResponse.json({ job: id, status: row.status, position }, { status: 202 });
}

// Clerk v5 exports clerkClient as an object, v6 as a function. Support both.
async function ownerEmail(userId: string): Promise<string> {
  try {
    const cc: any = typeof clerkClient === "function" ? await (clerkClient as any)() : clerkClient;
    const u = await cc.users.getUser(userId);
    return u?.emailAddresses?.[0]?.emailAddress || "";
  } catch (e) {
    console.error("[mail] could not resolve email", e);
    return "";
  }
}

// Best-effort: a mail failure must never break the render or the response.
async function notify(userId: string, status: "ready" | "failed", opts?: any) {
  const to = await ownerEmail(userId);
  if (!to) return;
  await sendRenderEmail(to, status, opts);
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

  // The row is marked running BEFORE Modal's job id is stored. Polling in
  // that window asks Modal with an empty id, gets "none", and would mark a
  // perfectly healthy render as failed. Wait for the id.
  if (!row.runner_job) {
    return NextResponse.json({ ...row, position: 0 });
  }
  const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 1, [502, 503, 504], 20000);
  const d = r.ok ? r.data : null;

  if (d && d.status === "done" && d.url) {
    // RETURNING id -> empty means another poll already flipped it, so we
    // email exactly once instead of on every 5s poll.
    const tr = (await sql`UPDATE mix_jobs SET status='done', url=${d.url},
              result=${JSON.stringify(d.result || {})}::jsonb, updated_at=NOW()
              WHERE id=${id} AND status <> 'done' RETURNING id`) as any[];
    if (tr.length && !row.max_seconds) await notify(userId, "ready", { url: d.url });
  } else if (d && d.status === "failed") {
    const err = String(d.error || "mix failed");
    await failJob(id, err);
    if (!row.max_seconds) await notify(userId, "failed", { error: err });
  } else if (d && d.status === "none") {
    // Only believe "none" once the job is old enough that Modal must have
    // registered it. Below that it is a startup race, not a failure.
    const ag = (await sql`SELECT EXTRACT(EPOCH FROM (NOW() - created_at))::int AS age
      FROM mix_jobs WHERE id=${id}`) as any[];
    if (Number(ag[0]?.age || 0) > 180) {
      await failJob(id, "Mixer restarted before finishing - please try again");
    }
  }

  await pump();

  const after = (await sql`SELECT * FROM mix_jobs WHERE id=${id}`) as any[];
  return NextResponse.json({ ...(after[0] || row), position: 0 });
}
