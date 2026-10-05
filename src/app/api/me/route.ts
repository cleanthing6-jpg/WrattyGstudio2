import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";   // ownership must never be cached

// Single source of truth for "am I the owner" - the client must not guess.
export async function GET() {
  const { userId } = await auth();
  const ownerId = (process.env.OWNER_USER_ID || "user_3JwUmxdbT5FMshejHI7swJNHs9t").trim();
  return NextResponse.json({ isOwner: !!userId && userId === ownerId });
}
