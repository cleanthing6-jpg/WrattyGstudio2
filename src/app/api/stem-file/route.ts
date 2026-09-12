import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const id = req.nextUrl.searchParams.get("id") || "";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });
  const rows = (await sql`SELECT name, data FROM stem_files WHERE id = ${id}`) as any[];
  const row = rows[0];
  if (!row) return NextResponse.json({ error: "not found" }, { status: 404 });
  const buf = Buffer.from(row.data, "base64");
  const lower = String(row.name || "").toLowerCase();
  const ct = lower.endsWith(".mp3") ? "audio/mpeg" : lower.endsWith(".flac") ? "audio/flac" : "audio/wav";
  return new Response(new Uint8Array(buf), {
    headers: { "Content-Type": ct, "Content-Length": String(buf.length), "Cache-Control": "no-store" },
  });
}
