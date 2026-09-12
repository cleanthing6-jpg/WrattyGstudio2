import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const maxDuration = 60;

const TONN = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";
const OWNER = process.env.OWNER_USER_ID || "";
const MAX_POLLS = 20;

const MIX_LIMIT: Record<string, number> = {
  free: 0,
  starter: 0,
  pro: 0,
  studio: 1,
};

async function tonnPost(path: string, body: unknown) {
  const res = await fetch(TONN + path, {
    method: "POST",
    headers: {
      "X-API-Key": KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

const isOwner = (userId: string) => {
  return OWNER.length > 0 && userId === OWNER;
};
async function ensureTable() {
  await sql`CREATE TABLE IF NOT EXISTS roex_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    url TEXT,
    body TEXT,
    attempts INT NOT NULL DEFAULT 0,
    reserved INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
  )`;
}

async function reserve(userId: string) {
  if (isOwner(userId)) return { ok: true as const };
  const rows = (await sql`
    SELECT tier, mixes_used FROM users
    WHERE id = ${userId}
  `) as any[];
  const row = rows[0];
  const used = row?.mixes_used ?? 0;
  const limit = MIX_LIMIT[row?.tier || "free"] ?? 0;
  if (used >= limit) {
    return { ok: false as const, error: "No mix credits left" };
  }
  await sql`
    UPDATE users SET mixes_used = mixes_used + 1
    WHERE id = ${userId}
  `;
  return { ok: true as const };
}

async function release(userId: string) {
  if (isOwner(userId)) return;
  await sql`
    UPDATE users
    SET mixes_used = GREATEST(0, mixes_used - 1)
    WHERE id = ${userId}
  `;
}
function buildBody(taskId: string, stems: any[]) {
  return {
    applyAudioEffectsData: {
      multitrackTaskId: taskId,
      trackData: stems.map((s: any) => {
        return { trackURL: s.url };
      }),
      returnStems: false,
    createMaster: true,
    desiredLoudness: "HIGH",
    },
  };
}

function pickUrl(r: any) {
  if (r.ok === false) return "";
  const res = r.data && r.data.applyAudioEffectsResults;
  return (res && res.download_url_mixed) || "";
}

export async function POST(req: NextRequest) {
  try {
    const authRes = await auth();
    const userId = authRes.userId;
    if (userId === null || userId === undefined) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const payload = await req.json();
    const taskId = payload.taskId;
    const rawStems = payload.stems;
    const stems = Array.isArray(rawStems) ? rawStems : [];
    const hasTask = typeof taskId === "string" && taskId.length > 0;
    if (hasTask === false || stems.length < 2) {
      return NextResponse.json(
        { error: "taskId + 2 stems required" },
        { status: 400 }
      );
    }

    await ensureTable();

    const found = (await sql`
      SELECT status, url FROM roex_jobs
      WHERE id = ${taskId} AND user_id = ${userId}
    `) as any[];
    const j = found[0];
    if (j) {
      if (j.status === "done" && j.url) {
        return NextResponse.json({ status: "done", url: j.url });
      }
      return NextResponse.json({ status: "pending" });
    }

    const gate = await reserve(userId);
    if (gate.ok === false) {
      return NextResponse.json(
        { error: gate.error },
        { status: 403 }
      );
    }

    const body = buildBody(taskId, stems);
    const bodyJson = JSON.stringify(body);
    const reserved = isOwner(userId) ? 0 : 1;

    await sql`
      INSERT INTO roex_jobs
        (id, user_id, status, body, reserved)
      VALUES
        (${taskId}, ${userId}, 'pending',
         ${bodyJson}, ${reserved})
    `;

    const r1 = await tonnPost("/retrievefinalmix", body);
    const url1 = pickUrl(r1);

    if (url1.length > 0) {
      await sql`
        UPDATE roex_jobs SET status = 'done', url = ${url1}
        WHERE id = ${taskId}
      `;
      return NextResponse.json({ status: "done", url: url1 });
    }

    const badReq = r1.status === 400 || r1.status === 401;
    if (r1.ok === false && badReq) {
      await sql`
        UPDATE roex_jobs SET status = 'failed'
        WHERE id = ${taskId}
      `;
      await release(userId);
      const raw = JSON.stringify(r1.data).slice(0, 300);
      return NextResponse.json(
        { error: "RoEx: " + raw },
        { status: r1.status || 502 }
      );
    }

    return NextResponse.json({ status: "pending" });
  } catch (e: any) {
    return NextResponse.json(
      { error: (e && e.message) || "RoEx mix failed" },
      { status: 500 }
    );
  }
}
export async function GET(req: NextRequest) {
  try {
    const authRes = await auth();
    const userId = authRes.userId;
    if (userId === null || userId === undefined) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const taskId = req.nextUrl.searchParams.get("taskId") || "";
    if (taskId === "") {
      return NextResponse.json(
        { error: "taskId required" },
        { status: 400 }
      );
    }

    const rows = (await sql`
      SELECT status, url, body, attempts, reserved
      FROM roex_jobs
      WHERE id = ${taskId} AND user_id = ${userId}
    `) as any[];
    const job = rows[0];
    if (job === undefined) {
      return NextResponse.json(
        { error: "Unknown job" },
        { status: 404 }
      );
    }
    if (job.status === "done" && job.url) {
      return NextResponse.json({ status: "done", url: job.url });
    }
    if (job.status === "failed") {
      return NextResponse.json(
        { error: "Mix failed - credit returned" },
        { status: 502 }
      );
    }

    const attempts = (job.attempts || 0) + 1;
    await sql`
      UPDATE roex_jobs SET attempts = ${attempts}
      WHERE id = ${taskId}
    `;

    const body = JSON.parse(job.body || "{}");
    const r2 = await tonnPost("/retrievefinalmix", body);
    const url2 = pickUrl(r2);

    if (url2.length > 0) {
      await sql`
        UPDATE roex_jobs SET status = 'done', url = ${url2}
        WHERE id = ${taskId}
      `;
      return NextResponse.json({ status: "done", url: url2 });
    }

    const badReq = r2.status === 400 || r2.status === 401;
    const dead = (r2.ok === false && badReq) || attempts >= MAX_POLLS;
    if (dead) {
      await sql`
        UPDATE roex_jobs SET status = 'failed'
        WHERE id = ${taskId}
      `;
      if (job.reserved) await release(userId);
      return NextResponse.json(
        { error: "Mix failed - credit returned" },
        { status: 502 }
      );
    }

    return NextResponse.json({
      status: "pending",
      attempt: attempts,
    });
  } catch (e: any) {
    return NextResponse.json(
      { error: (e && e.message) || "Poll failed" },
      { status: 500 }
    );
  }
}
