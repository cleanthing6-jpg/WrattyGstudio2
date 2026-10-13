import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { sql } from "@/lib/db";
import { fxTicket } from "@/lib/fxTicket";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Auth + ownership check, then hand the browser a 302 to the Modal files
// app with a short-lived read ticket in the URL. The file itself never
// travels through this route, so Render bandwidth stays near zero.
const clean = (s: string) =>
  (s || "").normalize("NFC").replace(/[/\\:*?"<>|\x00-\x1f]/g, "-")
    .replace(/\s+/g, " ").trim().replace(/^\.+|\.+$/g, "").slice(0, 80);

function fromRow(row: any): { mp3: string; flac: string } {
  let r: any = row?.result;
  if (typeof r === "string") { try { r = JSON.parse(r); } catch { r = {}; } }
  const f = (r && r.files) || {};
  return { mp3: String(f.mp3 || ""), flac: String(f.flac || "") };
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> }
) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { id } = await ctx.params;
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  const rows = (await sql`
    SELECT artist_name, song_title, url, result FROM mix_jobs
    WHERE id = ${id} AND user_id = ${userId}
  `) as any[];
  if (!rows.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
  const row = rows[0];

  const fmt = (req.nextUrl.searchParams.get("format") || "mp3").toLowerCase();
  const src = fmt === "flac" ? fromRow(row).flac : fromRow(row).mp3;
  const target = src || String(row.url || "");
  if (!target) return NextResponse.json({ error: "No file for this render" }, { status: 404 });

  const artist = clean(String(row.artist_name || ""));
  const title = clean(String(row.song_title || ""));
  const base = artist && title ? `${artist} - ${title}` : title || artist || "My mix";
  const name = `${base}.${fmt === "flac" ? "flac" : "mp3"}`;

  const tk = fxTicket("read");
  if (!tk) return NextResponse.json({ error: "ticket unavailable" }, { status: 502 });

  const u = new URL(target);
  u.searchParams.set("t", tk);
  u.searchParams.set("name", name);

  // 302 to the Modal files app — the browser downloads directly from Modal.
  return NextResponse.redirect(u.toString(), 302);
}
