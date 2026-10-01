import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { checkCredit } from "@/lib/credits";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const mix = await checkCredit(userId, "mix");
  const master = await checkCredit(userId, "master");

  return NextResponse.json({
    tier: mix.tier,
    mixes_used: mix.used,
    mixes_left: mix.limit,
    masters_used: master.used,
    masters_left: master.limit,
  });
}
