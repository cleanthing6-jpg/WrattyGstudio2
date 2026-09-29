import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { randomUUID } from "crypto";
import { r2, R2_BUCKET } from "@/lib/r2";
import { sql } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function ensureTable() {
  await sql`CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    r2_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
  )`;
  await sql`CREATE INDEX IF NOT EXISTS files_user_idx ON files (user_id)`;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!R2_BUCKET) return NextResponse.json({ error: "R2 not configured" }, { status: 500 });

  const body = await req.json().catch(() => ({}));
  const rawName = String(body.name || "stem.wav");
  const type = String(body.type || "application/octet-stream");

  const dot = rawName.lastIndexOf(".");
  const ext = dot >= 0 ? rawName.slice(dot).toLowerCase() : "";
  const base =
    rawName.slice(0, dot >= 0 ? dot : rawName.length)
      .replace(/[^A-Za-z0-9._-]/g, "_")
      .slice(0, 60) || "stem";

  const key = `stems/${userId}/${Date.now()}-${Math.random().toString(36).slice(2, 8)}-${base}${ext}`;
  const id = randomUUID();

  await ensureTable();
  await sql`INSERT INTO files (id, user_id, name, r2_key)
            VALUES (${id}, ${userId}, ${rawName}, ${key})
            ON CONFLICT DO NOTHING`;

  const url = await getSignedUrl(
    r2,
    new PutObjectCommand({ Bucket: R2_BUCKET, Key: key, ContentType: type }),
    { expiresIn: 600 }
  );

  const getUrl = await getSignedUrl(
    r2,
    new GetObjectCommand({ Bucket: R2_BUCKET, Key: key }),
    { expiresIn: 60 * 60 * 24 * 7 }
  );

  return NextResponse.json({ url, getUrl, key, id });
}
