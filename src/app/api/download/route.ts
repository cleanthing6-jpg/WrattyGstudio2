import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { sql } from "@/lib/db";
import { getMongoClient } from "@/lib/mongodb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Same-origin audio proxy. Browsers IGNORE the HTML download="..." attribute
// for cross-origin files, and *.modal.run is a different origin - so pointing
// at it directly could never give the file a real name. We fetch server-side
// and set Content-Disposition ourselves. Also lets us gate the Modal host
// later without breaking saved links.
const FILES_HOSTS = new Set(
  [process.env.FILES_BASE_URL || "https://wrattyg--wratty-files-web.modal.run"]
    .map((u) => { try { return new URL(u).host; } catch { return ""; } })
    .filter(Boolean)
);

const safeName = (s: string) =>
  (s || "").normalize("NFC")
    .replace(/[/\\:*?"<>|\x00-\x1f]/g, "-")
    .replace(/\s+/g, " ").trim()
    .replace(/^\.+|\.+$/g, "").slice(0, 80);

const rfc5987 = (s: string) =>
  encodeURIComponent(s).replace(/['()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());

function disposition(name: string, dl: boolean) {
  const ascii = name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "'");
  return (dl ? "attachment" : "inline") +
    '; filename="' + ascii + '"' +
    "; filename*=UTF-8''" + rfc5987(name);
}

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const id = req.nextUrl.searchParams.get("id") || "";
  const fmt = req.nextUrl.searchParams.get("format") === "flac" ? "flac" : "mp3";
  const dl = req.nextUrl.searchParams.get("dl") === "1";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  let target = "";
  let a = "";
  let t = "";
  let label = "";

  if (id.startsWith("job:")) {
    // Finished engine render - Postgres holds the names and both URLs.
    const rows = (await sql`
      SELECT artist_name, song_title, url, mp3_key, flac_key, result FROM mix_jobs
      WHERE id = ${id.slice(4)} AND user_id = ${userId}`) as any[];
    if (!rows.length) return NextResponse.json({ error: "Not found" }, { status: 404 });
    const row = rows[0];

    let res: any = row.result;
    if (typeof res === "string") { try { res = JSON.parse(res); } catch { res = {}; } }
    const files = (res && res.files) || {};

    // EXACT format only - an "MP3" button must never hand back a FLAC.
    target = String(fmt === "flac" ? (row.flac_key || files.flac || "") : (row.mp3_key || files.mp3 || ""));
    if (!/^https:\/\//.test(target)) {
      return NextResponse.json({ error: "No " + fmt.toUpperCase() + " stored for this render" }, { status: 404 });
    }
    a = String(row.artist_name || "").trim();
    t = String(row.song_title || "").trim();
    label = a && t ? a + " - " + t : t || a;
  } else {
    // Legacy dashboard entry - Mongo record must belong to this user and
    // point only at the files host.
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

  const ext = /\.flac$/i.test(u.pathname) ? "flac" : /\.mp3$/i.test(u.pathname) ? "mp3" : fmt;

  const range = req.headers.get("range");
  let up: Response;
  try {
    up = await fetch(target, { cache: "no-store", redirect: "manual", headers: range ? { Range: range } : undefined });
  } catch { return NextResponse.json({ error: "Upstream unreachable" }, { status: 502 }); }
  if (up.status === 416) {
    // A bad seek is not our failure - hand the browser the real answer.
    const h = new Headers();
    const cr = up.headers.get("content-range");
    if (cr) h.set("content-range", cr);
    return new Response(up.body, { status: 416, headers: h });
  }
  if (up.status !== 200 && up.status !== 206) {
    console.error("[download] upstream", up.status, target);
    return NextResponse.json({ error: "Upstream " + up.status }, { status: 502 });
  }

  const base = safeName(label) || "mix";
  const name = base + "." + ext;

  const headers = new Headers();
  headers.set("content-type", ext === "flac" ? "audio/flac" : "audio/mpeg");
  for (const h of ["content-length", "content-range", "accept-ranges"]) {
    const v = up.headers.get(h);
    if (v) headers.set(h, v);
  }
  headers.set("cache-control", "private, no-store");
  headers.set("content-disposition", disposition(name, dl));
  console.log("[download]", id, fmt, up.status, name);

  return new Response(up.body, { status: up.status, headers });
}
