import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { r2, R2_BUCKET } from "@/lib/r2";
import { sql } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  // Playback fallback: an <audio> tag may still be holding an EXPIRED
  // presigned R2 url. Recover the key from its path, prove ownership via
  // the DB, then mint a FRESH short-lived signature. The supplied URL is
  // only used to RECOVER A KEY - it is never trusted for authorization.
  const u = req.nextUrl.searchParams.get("u") || "";
  if (u) {
    let parsed: URL;
    try { parsed = new URL(u); } catch { return NextResponse.json({ error: "bad url" }, { status: 400 }); }
    let key = decodeURIComponent(parsed.pathname).replace(/^\/+/, "");
    if (R2_BUCKET && key.startsWith(R2_BUCKET + "/")) key = key.slice(R2_BUCKET.length + 1);
    const m = key.match(/(?:^|\/)((?:stems|masters)\/.+)$/);
    if (!m) return NextResponse.json({ error: "not a stem/master url" }, { status: 400 });
    key = m[1];
    const rows = (await sql`
      SELECT r2_key FROM files WHERE user_id = ${userId} AND r2_key = ${key} LIMIT 1
    `) as any[];
    if (!rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });
    const fresh = await getSignedUrl(
      r2,
      new GetObjectCommand({ Bucket: R2_BUCKET, Key: rows[0].r2_key }),
      { expiresIn: 3600 }
    );
    return NextResponse.redirect(fresh, 302);
  }

  const id = req.nextUrl.searchParams.get("id") || "";
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  const rows = (await sql`
    SELECT r2_key FROM files WHERE id = ${id} AND user_id = ${userId}
  `) as any[];
  if (!rows[0]) return NextResponse.json({ error: "not found" }, { status: 404 });

  const url = await getSignedUrl(
    r2,
    new GetObjectCommand({ Bucket: R2_BUCKET, Key: rows[0].r2_key }),
    { expiresIn: 3600 }
  );

  return NextResponse.redirect(url);
}
