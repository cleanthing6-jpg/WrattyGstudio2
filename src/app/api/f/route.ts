import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { getMongoClient } from "@/lib/mongodb";
import { fxTicket } from "@/lib/fxTicket";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Same-origin proxy for OLD dashboard entries, which stored a raw
// *.modal.run link. Two jobs: give the file a real name (browsers ignore
// download="..." cross-origin) and let us gate the Modal host later without
// breaking these links.
const ALLOWED = new Set([
  (process.env.FILES_BASE_URL || "https://wrattyg--wratty-files-web.modal.run").replace(/\/+$/, ""),
]);

const clean = (s: string) =>
  (s || "").normalize("NFC").replace(/[/\\:*?"<>|\x00-\x1f]/g, "-")
    .replace(/\s+/g, " ").trim().replace(/^\.+|\.+$/g, "").slice(0, 80);

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const raw = req.nextUrl.searchParams.get("u") || "";
  let target: URL;
  try { target = new URL(raw); } catch { return NextResponse.json({ error: "bad url" }, { status: 400 }); }
  if (!ALLOWED.has(target.origin)) return NextResponse.json({ error: "host not allowed" }, { status: 400 });

  // Not an open relay: the URL must appear on one of THIS user's mixes.
  const client = await getMongoClient();
  const owns = await client.db("wrattyg").collection("mixes").countDocuments({
    userId, $or: [{ url: raw }, { mp3: raw }, { flac: raw }],
  });
  if (!owns) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const tk = fxTicket("read");
  const up = await fetch(raw, {
    cache: "no-store",
    redirect: "manual",
    headers: {
      ...(req.headers.get("range") ? { Range: req.headers.get("range")! } : {}),
      ...(tk ? { "x-fx-ticket": tk } : {}),
    },
  });
  const ctype = up.headers.get("content-type") || "";
  if (!up.ok || !up.body || ctype.includes("text/html")) {
    return NextResponse.json({ error: "upstream " + up.status }, { status: 502 });
  }

  const h = new Headers();
  h.set("Content-Type", ctype || "application/octet-stream");
  h.set("Cache-Control", "private, no-store");
  h.set("Accept-Ranges", up.headers.get("accept-ranges") || "bytes");
  const cl = up.headers.get("content-length");
  if (cl) h.set("Content-Length", cl);
  const cr = up.headers.get("content-range");
  if (cr) h.set("Content-Range", cr);

  // Inline for <audio>, attachment only when a download is requested.
  if (req.nextUrl.searchParams.get("download") === "1") {
    const name = clean(req.nextUrl.searchParams.get("name") || "download") || "download";
    h.set("Content-Disposition",
      `attachment; filename="${name.replace(/[^\x20-\x7e]/g, "_").replace(/"/g, "")}"; ` +
      `filename*=UTF-8''${encodeURIComponent(name)}`);
  }

  return new NextResponse(up.body, { status: up.status === 206 ? 206 : 200, headers: h });
}
