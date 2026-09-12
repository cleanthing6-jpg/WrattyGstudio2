import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const maxDuration = 60;

const CAP_BYTES = 250000000;

async function ensureTables() {
  await sql`CREATE TABLE IF NOT EXISTS stem_chunks (
    upload_id TEXT NOT NULL,
    idx INT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (upload_id, idx)
  )`;
  await sql`CREATE TABLE IF NOT EXISTS stem_files (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  )`;
}

export async function POST(req: NextRequest) {
  try {
    try {
      const a: any = await auth();
      if (a && a.userId) console.log("[STEM-UPLOAD] user=" + a.userId);
    } catch (e) {
      console.log("[STEM-UPLOAD] auth check skipped");
    }

    const b = await req.json();
    const uploadId = String(b.uploadId || "");
    const name = String(b.name || "stem.wav");
    const index = Number(b.index);
    const total = Number(b.total);
    const data = String(b.data || "");
    if (!uploadId || !isFinite(index) || !isFinite(total) || total < 1) {
      return NextResponse.json({ error: "uploadId, index, total required" }, { status: 400 });
    }

    await ensureTables();

    const tot = (await sql`SELECT COALESCE(SUM(LENGTH(data)), 0) AS t FROM stem_files`) as any[];
    const used = Number((tot[0] && tot[0].t) || 0);
    if (used > CAP_BYTES) {
      return NextResponse.json({ error: "Storage is busy - try again in a few minutes" }, { status: 507 });
    }

    await sql`INSERT INTO stem_chunks (upload_id, idx, data) VALUES (${uploadId}, ${index}, ${data})
              ON CONFLICT (upload_id, idx) DO UPDATE SET data = ${data}`;

    if (index < total - 1) return NextResponse.json({ ok: true, part: index + 1, of: total });

    const rows = (await sql`SELECT data FROM stem_chunks WHERE upload_id = ${uploadId} ORDER BY idx`) as any[];
    const b64 = rows.map((r: any) => r.data).join("");
    await sql`DELETE FROM stem_chunks WHERE upload_id = ${uploadId}`;

    const id = uploadId + "-" + Date.now().toString(36);
    await sql`INSERT INTO stem_files (id, name, data) VALUES (${id}, ${name}, ${b64})`;
    await sql`DELETE FROM stem_files WHERE created_at < NOW() - INTERVAL '3 hours'`;

    const origin = new URL(req.url).origin;
    console.log("[STEM-UPLOAD] done name=" + name + " chars=" + b64.length);
    return NextResponse.json({ url: origin + "/api/stem-file?id=" + encodeURIComponent(id), name, bytes: b64.length });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || "stem upload failed" }, { status: 500 });
  }
}
