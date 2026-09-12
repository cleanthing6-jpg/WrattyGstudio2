import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const { userId } = await auth();
  const owner = process.env.OWNER_USER_ID || "";
  let tier = "";
  let used = 0;
  try {
    const rows = (await sql`SELECT tier, mixes_used FROM users WHERE id = ${userId}`) as any[];
    tier = rows[0]?.tier || "";
    used = rows[0]?.mixes_used ?? 0;
  } catch {}
  return NextResponse.json({
    userId,
    ownerSet: owner.length > 0,
    ownerLen: owner.length,
    ownerTail: owner.slice(-6),
    match: !!owner && userId === owner,
    tier,
    mixesUsed: used,
  });
}
