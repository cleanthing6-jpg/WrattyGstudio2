import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { sql } from "@/lib/db";
export async function GET() {
  const { userId } = await auth();
  const owner = (process.env.OWNER_USER_ID || "").trim();
  if (!owner || userId !== owner)
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  try {
    await sql`CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, tier TEXT DEFAULT 'free', beats_used INT DEFAULT 0, covers_used INT DEFAULT 0, mixes_used INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())`;
    await sql`CREATE TABLE IF NOT EXISTS generations (id SERIAL PRIMARY KEY, user_id TEXT, type TEXT, result_url TEXT, prompt TEXT, created_at TIMESTAMP DEFAULT NOW())`;
    return NextResponse.json({ ok: true });
  } catch (e: unknown) { return NextResponse.json({ error: e instanceof Error ? e.message : "Request failed" }, { status: 500 }); }
}
