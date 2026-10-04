import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { sql } from "@/lib/db";
import { getMongoClient } from "@/lib/mongodb";
import { sendAlert } from "@/lib/alert";

export const runtime = "nodejs";
export const maxDuration = 60;

const SECRET = process.env.FX_INTERNAL_SECRET || "";
const CLEANUP = (
  process.env.MODAL_CLEANUP_URL || "https://wrattyg--wratty-cleanup-api.modal.run"
).replace(/\/+$/, "");

function authed(req: NextRequest): boolean {
  if (!SECRET) return false;
  const got = req.headers.get("authorization") || "";
  const want = "Bearer " + SECRET;
  if (got.length !== want.length) return false;
  try {
    return crypto.timingSafeEqual(Buffer.from(got), Buffer.from(want));
  } catch {
    return false;
  }
}

// Renders live on the Modal volume as fx/<uuid>-mix-mp3.mp3 / .flac
const KEY_RE = /wratty-files-web\.modal\.run\/f\/(fx\/[^?#\s"']+\.(?:mp3|flac))/g;

function keysOf(row: any): string[] {
  const found = new Set<string>();
  for (const v of [row.mp3_key, row.flac_key, row.url]) {
    KEY_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = KEY_RE.exec(String(v || "")))) found.add(m[1]);
  }
  return Array.from(found);
}

async function runSweep(req: NextRequest) {
  if (!authed(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const live = body?.live === true;   // deletion only when explicitly asked

  // Never sweep while renders are in flight - the volume commit would race.
  const busy = (await sql`
    SELECT COUNT(*)::int AS n FROM mix_jobs WHERE status IN ('queued','running')
  `) as any[];
  const inFlight = Number(busy[0]?.n || 0);

  // updated_at = when the job actually finished, not when it was queued.
  // Full renders: 30 days. 30-second previews: 7 days (they are throwaway).
  const rows = (await sql`
    SELECT id, user_id, mp3_key, flac_key, url, updated_at
    FROM mix_jobs
    WHERE status = 'done'
      AND (
        (max_seconds IS NULL     AND updated_at < NOW() - INTERVAL '30 days')
        OR
        (max_seconds IS NOT NULL AND updated_at < NOW() - INTERVAL '7 days')
      )
    ORDER BY updated_at ASC
    LIMIT 200`) as any[];

  const plan = rows
    .map((r) => ({ id: r.id, when: r.updated_at, keys: keysOf(r) }))
    .filter((p) => p.keys.length > 0);

  if (!live) {
    return NextResponse.json({
      dryRun: true,
      inFlight,
      candidates: plan.length,
      totalKeys: plan.reduce((n, p) => n + p.keys.length, 0),
      sample: plan.slice(0, 10),
    });
  }

  if (inFlight > 0) {
    return NextResponse.json(
      { ok: false, skipped: "renders in flight", inFlight },
      { status: 409 }
    );
  }

  let deleted = 0;
  let kept = 0;
  const errors: string[] = [];

  for (const p of plan) {
    try {
      const c = await fetch(CLEANUP + "/delete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + SECRET,
        },
        body: JSON.stringify({ keys: p.keys }),
        signal: AbortSignal.timeout(30000),
      });
      const d: any = await c.json().catch(() => null);
      // The cleanup endpoint returns ok:true even when `bad` is non-empty.
      if (!c.ok || !d || (Array.isArray(d.bad) && d.bad.length)) {
        kept++;
        errors.push(p.id + ": file delete failed");
        continue;                 // keep the row so this is retried later
      }
      // Files are gone -> drop the Mongo doc, then the row.
      try {
        const client = await getMongoClient();
        await client.db("wrattyg").collection("mixes").deleteMany({ jobId: String(p.id) });
      } catch (e: any) {
        errors.push(p.id + ": mongo " + (e?.message || "failed"));
      }
      await sql`DELETE FROM mix_jobs WHERE id = ${p.id}`;
      deleted++;
    } catch (e: any) {
      kept++;
      errors.push(p.id + ": " + (e?.name || "") + " " + (e?.message || ""));
    }
  }

  if (kept > 0 || errors.length) {
    void sendAlert(
      "Retention sweep had problems",
      "deleted=" + deleted + " kept=" + kept + "\n" + errors.slice(0, 10).join("\n")
    );
  }
  return NextResponse.json({ ok: true, deleted, kept, errors: errors.slice(0, 20) });
}


export async function POST(req: NextRequest) {
  try {
    return await runSweep(req);
  } catch (e: any) {
    void sendAlert("Retention sweep crashed", String(e?.message || e));
    return NextResponse.json({ error: "sweep failed" }, { status: 500 });
  }
}
