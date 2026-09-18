import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const formData = await req.formData();
    const audio = formData.get("audio") as File;
    if (!audio) return NextResponse.json({ error: "No audio file" }, { status: 400 });
    return NextResponse.json({ message: "Audio received. Automix processing coming soon.", filename: audio.name });
  } catch (e: unknown) { return NextResponse.json({ error: e instanceof Error ? e.message : "Request failed" }, { status: 500 }); }
}
