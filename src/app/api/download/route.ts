import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import crypto from "crypto";
import { sql } from "@/lib/db";
import { getMongoClient } from "@/lib/mongodb";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The file host (Modal "wratty-files") gates GET /f/ behind a short-lived
// signed ticket, so the browser cannot fetch renders directly - it can't send
// the header, and a plain <audio src> gets 401. Everything therefore goes
// through this route, which mints the ticket server-side. The shared secret
// never reaches the client.
const BASE = (process.env.FILES_BASE_URL || "https://wrattyg--wratty-files-web.modal.run")
  .replace(/\/+$/, "");

const FILES_HOSTS = (() => {
  try { return new Set([new URL(BASE).host]); } catch { return new Set<string>(); }
})();

// ticket_ok() on the Modal side signs "<scope>|<exp>". The scope depends on
// which revision of modal_files.py is deployed, so we try "read" and fall
// back to the original "stem-upload". Signing is cheap; a wrong guess only
// costs one 401.
function ticket(scope: string, ttlSec = 600): string {
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

const rfc5987 = (s: string) =>
  encodeURIComponent(s).replace(/['()*]/g, (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase());

function disposition(name: string, dl: boolean) {
  const ascii = name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "'");
  return (dl ? "attachment" : "inline") +
    '; filename="' + ascii + '"' +
    "; filename*=UTF-8''" + rfc5987(name);
}

async function upstream(target: string, range: string | null): Promise<Response | null> {
  for (const scope of ["read", "stem-upload"]) {
    const tk = ticket(scope);
    const headers: Record<string, string> = {};
    if (range) headers["range"] = range;
    if (tk) headers["x-fx-ticket"] = tk;
    try {
      const up = await fetch(target, { cache: "no-store", redirect: "manual", headers });
      if (up.status !== 401) return up;   // only a ticket rejection is worth retrying
      console.warn("[download] 401 with scope", scope, target);
    } catch {
      return null;
    }
  }
  return null;
}

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

    // EXACT format only - an "MP3" request must never hand back a FLAC.
    target = String(fmt === "flac" ? (row.flac_key || files.flac || "") : (row.mp3_key || files.mp3 || ""));
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

  const ext = /\.flac$/i.test(u.pathname) ? "flac" : /\.mp3$/i.test(u.pathname) ? "mp3" : fmt;
  const up = await upstream(target, req.headers.get("range"));
  if (!up) return NextResponse.json({ error: "Upstream unreachable or ticket rejected" }, { status: 502 });

  if (up.status === 416) {
    const h = new Headers();
    const cr = up.headers.get("content-range");
    if (cr) h.set("content-range", cr);
    return new Response(up.body, { status: 416, headers: h });
  }
  if (up.status !== 200 && up.status !== 206) {
    console.error("[download] upstream", up.status, target);
    return NextResponse.json({ error: "Upstream " + up.status }, { status: 502 });
  }

  const name = (safeName(label) || "mix") + "." + ext;
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
