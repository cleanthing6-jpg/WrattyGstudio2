import { list, del } from "@vercel/blob";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret && request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const cutoff = Date.now() - MAX_AGE_MS;
  const doomed: string[] = [];
  let cursor: string | undefined;
  let scanned = 0;

  do {
    const page = await list({ prefix: "stems/", cursor, limit: 1000 });
    for (const b of page.blobs) {
      scanned++;
      if (new Date(b.uploadedAt).getTime() < cutoff) doomed.push(b.url);
    }
    cursor = page.cursor;
  } while (cursor);

  if (doomed.length) await del(doomed);
  return NextResponse.json({ scanned, deleted: doomed.length });
}
