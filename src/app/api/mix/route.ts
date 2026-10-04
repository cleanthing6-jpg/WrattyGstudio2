import { auth, clerkClient } from "@clerk/nextjs/server";
import { sendRenderEmail } from "@/lib/mail";
import { getMongoClient } from "@/lib/mongodb";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";
import { getUser, consumeCredit, refundCredit } from "@/lib/credits";
import { sendAlert } from "@/lib/alert";

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

// Renders run in their own Modal containers (2 CPU / 8GB each), NOT on
// Render. This cap is the only thing limiting how many run at once.
const MAX_RUNNING = 10;
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
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS artist_name TEXT`;
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS song_title  TEXT`;
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS mode TEXT`;
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS flac_key    TEXT`;
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS mp3_key     TEXT`;
  // Dismissed renders stay in the table (the file is still there) but drop
  // off the dashboard list.
  await sql`ALTER TABLE mix_jobs ADD COLUMN IF NOT EXISTS hidden_at   TIMESTAMP`;
  await sql`CREATE TABLE IF NOT EXISTS preview_quota (
    user_id TEXT NOT NULL,
    day DATE NOT NULL,
    used INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
  )`;
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
  // Alert the OWNER (throttled to 1/hour) without blocking the refund.
  void sendAlert("A mix failed", "job " + id + "\n" + error);
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
      WHERE status='running' AND (updated_at < NOW() - INTERVAL '70 minutes' OR created_at < NOW() - INTERVAL '75 minutes')
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
        WHERE status='running' AND updated_at > NOW() - INTERVAL '70 minutes') < ${MAX_RUNNING}
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
    .filter((s: any) => {
      // The Modal worker FETCHES this url, so an arbitrary https url is an
      // SSRF vector. Block loopback / private / link-local targets - the
      // cloud metadata endpoint (169.254.169.254) is the one that matters
      // most. Every legitimate external host (R2, the splitter) still passes.
      if (!/^https:\/\//.test(s.url)) return false;
      try {
        const h = new URL(s.url).hostname.toLowerCase();
        if (!h) return false;
        if (h === "localhost" || h.endsWith(".localhost") ||
            h.endsWith(".local") || h.endsWith(".internal")) return false;
        if (/^(127|10)\./.test(h)) return false;
        if (/^192\.168\./.test(h)) return false;
        if (/^172\.(1[6-9]|2\d|3[01])\./.test(h)) return false;
        if (/^169\.254\./.test(h)) return false;
        if (h === "0.0.0.0" || h === "::1" || h === "[::1]") return false;
        if (h.startsWith("fc") || h.startsWith("fd") || h.startsWith("fe80")) return false;
        return true;
      } catch { return false; }
    });
  if (!stems.length) return NextResponse.json({ error: "stems[] with https urls required" }, { status: 400 });

  const loudness = String(body?.loudness || "MEDIUM").toUpperCase();
  const preset = body?.preset ? String(body.preset) : "afrobeats";
  // Display name for the finished downloads. Sanitised HERE so the browser
  // can never inject a path separator or a control character.
  const artist = String(body?.artist || "")
    .replace(/[^\p{L}\p{N} ._&'()-]/gu, "").trim().slice(0, 60);
  const title = String(body?.title || "")
    .replace(/[^\p{L}\p{N} ._&'()-]/gu, "").trim().slice(0, 60);
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
      // Atomic: the ON CONFLICT takes a row lock, so two concurrent requests
      // serialise and cannot both read "9". RETURNING is empty when the WHERE
      // fails - that is our signal the day's 10 slots are gone. No refund on
      // failure: a slot covers the ATTEMPT (exactly like the old count-all
      // query did) and it closes the fail-to-regain-slots loop.
      const claimed = (await sql`
        INSERT INTO preview_quota (user_id, day, used)
        VALUES (${userId}, (NOW() AT TIME ZONE 'UTC')::date, 1)
        ON CONFLICT (user_id, day)
        DO UPDATE SET used = preview_quota.used + 1
          WHERE preview_quota.used < 10
        RETURNING used`) as any[];
      if (!claimed.length) {
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
    await sql`INSERT INTO mix_jobs (id, user_id, status, stems, loudness, preset, max_seconds, credit_type, artist_name, song_title, mode)
      VALUES (${id}, ${userId}, 'queued', ${JSON.stringify(stems)}::jsonb, ${loudness}, ${preset}, ${maxSeconds}, ${creditType}, ${artist || null}, ${title || null}, ${mode})`;
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

// Full renders are listed on the dashboard (Mongo `mixes`, read by
// /api/mixes). Previews are not. Best-effort: a Mongo hiccup must never
// break the render poll.
async function saveToDashboard(
  userId: string, row: any, mp3: string, flac: string
): Promise<{ saved: boolean; name: string }> {
  const a = String(row?.artist_name || "").trim();
  const t = String(row?.song_title || "").trim();
  const name = a && t ? `${a} - ${t}` : t || a || "My mix";
  const jobId = String(row?.id || "");
  if (!jobId || (!mp3 && !flac)) return { saved: false, name };
  try {
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    try {
      await col.createIndex({ userId: 1, jobId: 1 }, { unique: true });
    } catch (ie) {
      console.error("[mixes] index not created (dupes?)", ie);
    }
    await col.updateOne(
      { userId, jobId },
      {
        $set: {
          name, url: mp3 || flac, mp3: mp3 || "", flac: flac || "",
          loudness: String(row?.loudness || ""), preset: String(row?.preset || ""),
          mode: String(row?.mode || ""),
        },
        $setOnInsert: { userId, jobId, createdAt: new Date() },
      },
      { upsert: true },
    );
    return { saved: true, name };
  } catch (e) {
    console.error("[mixes] dashboard save failed", { jobId, error: e });
    return { saved: false, name };
  }
}


function filesOf(row: any) {
  let result: any = row && row.result;
  if (typeof result === "string") {
    try { result = JSON.parse(result); } catch { result = {}; }
  }
  const files = (result && result.files) || {};
  const src = String((row && row.url) || "");
  const low = src.toLowerCase();
  return {
    mp3: String((row && row.mp3_key) || files.mp3 || (low.indexOf(".mp3") >= 0 ? src : "")),
    flac: String((row && row.flac_key) || files.flac || (low.indexOf(".flac") >= 0 ? src : "")),
  };
}


function clientJobResponse(row: any) {
  if (!row || !row.id) return row;
  let result: any = row.result;
  if (typeof result === "string") {
    try { result = JSON.parse(result); } catch { result = null; }
  }
  const files = result && typeof result === "object" ? result.files : null;
  const sourceUrl = String(row.url || (result && result.url) || "");
  const isFlac = /\.flac(?:$|[?#])/i.test(sourceUrl);
  const rawMp3 = String(row.mp3_key || (files && files.mp3) || (isFlac ? "" : sourceUrl));
  const rawFlac = String(row.flac_key || (files && files.flac) || (isFlac ? sourceUrl : ""));
  const fileUrl = (f: "mp3" | "flac") =>
    "/api/download?id=" + encodeURIComponent("job:" + row.id) + "&format=" + f;
  const mp3 = rawMp3.indexOf("https://") === 0 ? fileUrl("mp3") : "";
  const flac = rawFlac.indexOf("https://") === 0 ? fileUrl("flac") : "";
  const publicUrl = (isFlac ? flac : mp3) || mp3 || flac;
  let safeResult = result;
  if (result && typeof result === "object") {
    safeResult = { ...result };
    if (files && typeof files === "object") {
      safeResult.files = { ...files };
      if (rawMp3) safeResult.files.mp3 = mp3;
      if (rawFlac) safeResult.files.flac = flac;
    }
    if (typeof safeResult.url === "string") safeResult.url = publicUrl;
  }
  return { ...row, url: publicUrl, mp3_key: mp3, flac_key: flac, result: safeResult };
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
    return NextResponse.json(clientJobResponse({ ...row, position: await positionOf(id) }));
  }
  if (row.status === "failed") {
    return NextResponse.json(clientJobResponse({ ...row, position: 0 }));
  }
  if (row.status === "done") {
    const f = filesOf(row);
    const saved = row.max_seconds
      ? { saved: false, name: "" }
      : await saveToDashboard(userId, row, f.mp3, f.flac);
    return NextResponse.json({
      ...clientJobResponse({ ...row, position: 0 }),
      dashboardSaved: saved.saved,
      dashboardName: saved.name,
    });
  }

  // The row is marked running BEFORE Modal's job id is stored. Polling in
  // that window asks Modal with an empty id, gets "none", and would mark a
  // perfectly healthy render as failed. Wait for the id.
  if (!row.runner_job) {
    return NextResponse.json(clientJobResponse({ ...row, position: 0 }));
  }
  const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 1, [502, 503, 504], 20000);
  const d = r.ok ? r.data : null;
  let dashboardSave: { saved: boolean; name: string } = { saved: false, name: "" };

  if (d && d.status === "done" && d.url) {
    // RETURNING id -> empty means another poll already flipped it, so we
    // email exactly once instead of on every 5s poll.
    // RETURNING id -> empty means another poll already flipped it, so we
    // save + email exactly once instead of on every 5s poll.
    const flacU = String(d.result?.files?.flac || "");
    const mp3U = String(d.result?.files?.mp3 || "");
    const tr = (await sql`UPDATE mix_jobs SET status='done', url=${d.url},
              flac_key=${flacU || null}, mp3_key=${mp3U || null},
              result=${JSON.stringify(d.result || {})}::jsonb, updated_at=NOW()
              WHERE id=${id} AND status <> 'done' RETURNING id`) as any[];
    if (!row.max_seconds) {
      dashboardSave = await saveToDashboard(userId, row, mp3U, flacU);
    }
    if (tr.length && !row.max_seconds) {
      await notify(userId, "ready", { url: mp3U || d.url });
    }
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
  return NextResponse.json({
    ...clientJobResponse({ ...(after[0] || row), position: 0 }),
    dashboardSaved: dashboardSave.saved,
    dashboardName: dashboardSave.name,
  });
}
