import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

const MVSEP_TOKEN = process.env.MVSEP_API_TOKEN || "";

// Free accounts get ONE full split per day. Anyone with a paid tier gets more.
// No queue, no global cap: this only stops one account farming the MVSEP quota.
const FREE_SPLITS_PER_DAY = 1;
const PAID_SPLITS_PER_DAY = 5;

let ready: Promise<void> | null = null;
function ensureTable() {
  if (!ready) {
    ready = (async () => {
      await sql`CREATE TABLE IF NOT EXISTS split_jobs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        mvsep_hash TEXT,
        status TEXT NOT NULL DEFAULT 'reserved',
        day TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      )`;
      await sql`CREATE INDEX IF NOT EXISTS split_jobs_user_day_idx ON split_jobs (user_id, day)`;
    })().catch((e) => { ready = null; throw e; });
  }
  return ready;
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    await ensureTable();

    const day = new Date().toISOString().slice(0, 10);
    const urows = (await sql`SELECT tier FROM users WHERE id = ${userId}`) as any[];
    const tier = String(urows[0]?.tier || "free");
    // The owner is never capped. Same OWNER_USER_ID the render route uses.
    const ownerId = (process.env.OWNER_USER_ID || "user_3JwUmxdbT5FMshejHI7swJNHs9t").trim();
    const isOwner = !!ownerId && userId === ownerId;
    const cap = isOwner ? 999999 : (tier === "free" ? FREE_SPLITS_PER_DAY : PAID_SPLITS_PER_DAY);

    // Reserve the slot BEFORE calling MVSEP. The WHERE clause makes this
    // atomic: no row is inserted once the cap is reached.
    const id = "sp_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    const ins = (await sql`
      INSERT INTO split_jobs (id, user_id, status, day)
      SELECT ${id}, ${userId}, 'reserved', ${day}
      WHERE (SELECT count(*) FROM split_jobs WHERE user_id = ${userId} AND day = ${day}) < ${cap}
      RETURNING id
    `) as any[];

    if (!ins.length) {
      return NextResponse.json(
        { error: cap === 1
            ? "You have used today\'s free split. Try again tomorrow."
            : "You have used today\'s splits. Try again tomorrow." },
        { status: 429 }
      );
    }

    const ct = req.headers.get("content-type") || "";
    const form = new FormData();
    form.append("api_token", MVSEP_TOKEN);
    form.append("sep_type", "40");

    if (ct.includes("application/json")) {
      const body = await req.json();
      const audioUrl = typeof body.audioUrl === "string" ? body.audioUrl.trim() : "";
      if (!audioUrl) return NextResponse.json({ error: "Missing audio URL" }, { status: 400 });
      form.append("url", audioUrl);
    } else {
      const fd = await req.formData();
      const file = fd.get("file") as File | null;
      if (!file) return NextResponse.json({ error: "No audio file" }, { status: 400 });
      const buf = Buffer.from(await file.arrayBuffer());
      form.append("audiofile", new Blob([buf], { type: file.type || "audio/mpeg" }), file.name || "track.mp3");
    }

    const res = await fetch("https://mvsep.com/api/separation/create", { method: "POST", body: form });
    const data = await res.json();
    const hash = data?.data?.hash || data?.hash;

    if (!hash) {
      // The job never started, so give the slot back - a failure must not
      // burn the user\'s daily allowance.
      await sql`DELETE FROM split_jobs WHERE id = ${id}`;
      return NextResponse.json({ error: "MVSEP: " + JSON.stringify(data).slice(0, 300) }, { status: 502 });
    }

    await sql`UPDATE split_jobs SET mvsep_hash = ${hash}, status = 'running' WHERE id = ${id}`;
    return NextResponse.json({ taskId: hash });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || "Stem split failed" }, { status: 500 });
  }
}
