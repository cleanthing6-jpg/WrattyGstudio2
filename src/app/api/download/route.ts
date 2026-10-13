import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import crypto from "crypto";
import { sql } from "@/lib/db";
import { getMongoClient } from "@/lib/mongodb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The Modal files app gates GET /f/ behind a short-lived HMAC ticket. It now
// accepts that ticket in the URL as ?t= as well as the x-fx-ticket header,
// so we can 302 the browser straight at Modal instead of streaming the file
// through this route. Render sees only the auth check, not the bytes.
const BASE = (process.env.FILES_BASE_URL || "https://wrattyg--wratty-files-web.modal.run")
  .replace(/\/+$/, "");

const FILES_HOSTS = (() => {
  try { return new Set([new URL(BASE).host]); } catch { return new Set<string>(); }
})();

function ticket(scope: string, ttlSec = 900): string {
  const key = process.env.FX_INTERNAL_SECRET || "";
  if (!key) return "";
  const exp = Math.floor(Date.now() / 1000) + ttlSec;
  const sig = crypto.createHmac("sha256", key).update(scope + "|" + exp).digest("hex");
  return exp + "." + sig;
}

const safeName = (s: string) =>
  (s || "").normalize("NFC")
    .replace(/[/\\:*?"<>|\x00-\x1f]/g, "-")
    .replace(/\s+/g, " ").trim()
    .replace(/^\.+|\.+$/g, "").slice(0, 80);

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const id = req.nextUrl.searchParams.get("id") || "";
  const fmt = req.nextUrl.searchParams.get("format") === "flac" ? "flac" : "mp3";
  const dl = req.nextUrl.searchParams.get("dl") === "1";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  let target = "";
  let label = "";

  if (id.startsWith("job:")) {
    const rows = (await sql`
      SELECT artist_name, song_title, url, mp3_key, flac_key, result FROM mix_jobs
      WHERE id = ${id.slice(4)} AND user_id = ${userId}`) as any[];
    if (!rows.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
    const row = rows[0];

    let res: any = row.result;
    if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
    const files = (res && res.files) || {};

    target = String(fmt === "flac"
      ? (row.flac_key || files.flac || "")
      : (row.mp3_key || files.mp3 || ""));
    if (!/^https:\/\//.test(target)) {
      return NextResponse.json({ error: "No " + fmt.toUpperCase() + " stored for this render" }, { status: 404 });
    }
    const a = String(row.artist_name || "").trim();
    const t = String(row.song_title || "").trim();
    label = a && t ? a + " - " + t : t || a;
  } else {
    let doc: any = null;
    try {
      const { ObjectId } = await import("mongodb");
      const client = await getMongoClient();
      doc = await client.db("wrattyg").collection("mixes").findOne({ _id: new ObjectId(id), userId });
    } catch { doc = null; }
    if (!doc) return NextResponse.json({ error: "Not found" }, { status: 404 });
    target = String(fmt === "flac" ? (doc.flac || "") : (doc.mp3 || doc.url || ""));
    if (!/^https:\/\//.test(target)) {
      return NextResponse.json({ error: "No " + fmt.toUpperCase() + " stored for this mix" }, { status: 404 });
    }
    label = String(doc.name || "");
  }

  let u: URL;
  try { u = new URL(target); } catch { return NextResponse.json({ error: "bad url" }, { status: 400 }); }
  if (!FILES_HOSTS.has(u.host)) return NextResponse.json({ error: "host not allowed" }, { status: 400 });

  const tk = ticket("read", 900);
  if (tk) u.searchParams.set("t", tk);

  const ext = /\.flac$/i.test(u.pathname) ? "flac" : /\.mp3$/i.test(u.pathname) ? "mp3" : fmt;
  const name = (safeName(label) || "mix") + "." + ext;
  if (dl) u.searchParams.set("name", name);

  console.log("[download] redirect", id, fmt, name);
  return NextResponse.redirect(u.toString(), 302);
}
