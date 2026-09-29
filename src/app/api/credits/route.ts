import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { checkCredit } from "@/lib/credits";
export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const mix = await checkCredit(userId, "mix");
  return NextResponse.json({ tier: mix.tier, beats_used: 0, beats_left: 0, covers_used: 0, covers_left: 0, mixes_used: mix.used, mixes_left: mix.limit - mix.used });
}
