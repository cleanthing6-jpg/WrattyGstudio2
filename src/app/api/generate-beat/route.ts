import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  try {
    const { prompt } = await req.json();
    const response = await fetch("https://api.aimlapi.com/v1/music/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.AIMLAPI_KEY}` },
      body: JSON.stringify({ model: "minimax-music-2.0", prompt, duration: 180, format: "mp3" }),
    });
    const data = await response.json();
    if (data.audio_url) return NextResponse.json({ url: data.audio_url });
    return NextResponse.json({ error: "Failed to generate beat" }, { status: 500 });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
