import { NextResponse } from "next/server";
import { sql } from "@/lib/db";
export async function GET() {
  try {
    await sql`CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, tier TEXT DEFAULT 'free', beats_used INT DEFAULT 0, covers_used INT DEFAULT 0, mixes_used INT DEFAULT 0, created_at TIMESTAMP DEFAULT NOW())`;
    await sql`CREATE TABLE IF NOT EXISTS generations (id SERIAL PRIMARY KEY, user_id TEXT, type TEXT, result_url TEXT, prompt TEXT, created_at TIMESTAMP DEFAULT NOW())`;
    return NextResponse.json({ ok: true });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
