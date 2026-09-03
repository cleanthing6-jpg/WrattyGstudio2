import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { sql } from "@/lib/db";
export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const items = await sql`SELECT * FROM generations WHERE user_id = ${userId} ORDER BY created_at DESC LIMIT 50`;
  return NextResponse.json({ items });
}
