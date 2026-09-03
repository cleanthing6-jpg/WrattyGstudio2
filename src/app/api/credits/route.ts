import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { checkCredit } from "@/lib/credits";
export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const [beat, cover, mix] = await Promise.all([checkCredit(userId, "beat"), checkCredit(userId, "cover"), checkCredit(userId, "mix")]);
  return NextResponse.json({ tier: beat.tier, beats_used: beat.used, beats_left: beat.limit - beat.used, covers_used: cover.used, covers_left: cover.limit - cover.used, mixes_used: mix.used, mixes_left: mix.limit - mix.used });
}
