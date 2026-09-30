import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export const runtime = "nodejs";

// Single source of truth for "am I the owner" - the client must not guess.
export async function GET() {
  const { userId } = await auth();
  const ownerId = (process.env.OWNER_USER_ID || "user_3IqTsednC0Bqdk3JMxeGzW6zdGD").trim();
  return NextResponse.json({ isOwner: !!userId && userId === ownerId });
}
