import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const audio = formData.get("audio") as File;
    if (!audio) return NextResponse.json({ error: "No audio file" }, { status: 400 });
    return NextResponse.json({ message: "Audio received. Automix processing coming soon.", filename: audio.name });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
