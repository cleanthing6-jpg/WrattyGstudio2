import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { sql } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// A same-origin download endpoint. This exists because browsers IGNORE the
// HTML download="..." attribute for cross-origin files, so pointing the
// dashboard straight at *.modal.run could never give the file a real name.
// Streaming it through here sets Content-Disposition properly.
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

  const up = await fetch(target, {
    cache: "no-store",
    headers: req.headers.get("range") ? { Range: req.headers.get("range")! } : undefined,
  });
  const ctype = up.headers.get("content-type") || "";
  const body = up.body;
  if (!up.ok || !body || ctype.includes("text/html")) {
    return NextResponse.json({ error: "upstream " + up.status }, { status: 502 });
  }

  const h = new Headers();
  h.set("Content-Type", ctype || (fmt === "flac" ? "audio/flac" : "audio/mpeg"));
  h.set("Cache-Control", "private, no-store");
  h.set(
    "Content-Disposition",
    `attachment; filename="${name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "")}"; ` +
      `filename*=UTF-8''${encodeURIComponent(name)}`
  );
  const cl = up.headers.get("content-length");
  if (cl) h.set("Content-Length", cl);
  const cr = up.headers.get("content-range");
  if (cr) h.set("Content-Range", cr);
  h.set("Accept-Ranges", up.headers.get("accept-ranges") || "bytes");

  return new NextResponse(body, { status: up.status === 206 ? 206 : 200, headers: h });
}
