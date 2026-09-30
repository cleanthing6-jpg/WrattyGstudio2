import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export const runtime = "nodejs";

export async function GET() {
  const { userId } = await auth();
  const ownerId = (process.env.OWNER_USER_ID || "").trim();
  return NextResponse.json({
    isOwner: !!userId && userId === ownerId,
    userId: userId || null,
    ownerConfigured: !!ownerId,
  });
}
