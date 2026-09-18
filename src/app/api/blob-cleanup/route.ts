import { del, list } from "@vercel/blob";
import { NextResponse } from "next/server";

const FX_MAX_AGE = 24 * 60 * 60 * 1000;      // renders: 24h
const PREVIEW_MAX_AGE = 6 * 60 * 60 * 1000;  // previews: 6h

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "CRON_SECRET not set" }, { status: 500 });
  }
  if (request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const now = Date.now();
  const rules = [
    { prefix: "fx/", maxAge: FX_MAX_AGE },
    { prefix: "previews/", maxAge: PREVIEW_MAX_AGE },
  ];

  let scanned = 0;
  let deleted = 0;
  let freed = 0;

  for (const rule of rules) {
    let cursor: string | undefined;
    do {
      const page = await list({ prefix: rule.prefix, limit: 1000, cursor });
      scanned += page.blobs.length;

      const doomed = page.blobs.filter(
        (b) => now - new Date(b.uploadedAt).getTime() > rule.maxAge
      );

      for (let i = 0; i < doomed.length; i += 100) {
        const batch = doomed.slice(i, i + 100);
        await del(batch.map((b) => b.url));
        deleted += batch.length;
        freed += batch.reduce((t, b) => t + b.size, 0);
      }

      cursor = page.cursor;
    } while (cursor);
  }

  return NextResponse.json({
    scanned,
    deleted,
    freedMB: Number((freed / 1048576).toFixed(1)),
    protected: ["stems/", "masters/"],
  });
}
