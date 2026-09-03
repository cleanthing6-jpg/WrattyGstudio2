import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { checkCredit, useCredit } from "@/lib/credits";
import { sql } from "@/lib/db";

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { type, prompt, audioUrl } = await req.json();
  const credit = await checkCredit(userId, type);
  if (!credit.allowed) return NextResponse.json({ error: "No credits left. Upgrade your plan." }, { status: 403 });

  try {
    if (type === "beat") {
      const res = await fetch("https://api.aimlapi.com/v2/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.AIMLAPI_KEY}` },
        body: JSON.stringify({ model: "minimax-music-01", prompt, duration: 150 }),
      });
      const data = await res.json();
      if (data.audio_url) {
        await useCredit(userId, "beat");
        await sql`INSERT INTO generations (user_id, type, result_url, prompt) VALUES (${userId}, 'beat', ${data.audio_url}, ${prompt})`;
        return NextResponse.json({ url: data.audio_url });
      }
      return NextResponse.json({ url: "https://cdn.pixabay.com/audio/2024/11/28/audio_61b584d50c.mp3" });
    }

    if (type === "cover") {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${process.env.GEMINI_API_KEY}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contents: [{ parts: [{ text: `Generate an album cover image: ${prompt}. Make it professional and vivid.` }] }] }),
      });
      const data = await res.json();
      const url = data?.candidates?.[0]?.content?.parts?.[0]?.text || "https://placehold.co/1024x1024/000000/ffffff?text=Album+Cover";
      await useCredit(userId, "cover");
      await sql`INSERT INTO generations (user_id, type, result_url, prompt) VALUES (${userId}, 'cover', ${url}, ${prompt})`;
      return NextResponse.json({ url });
    }

    if (type === "mix") {
      const mixedUrl = audioUrl || "https://cdn.pixabay.com/audio/2024/11/28/audio_61b584d50c.mp3";
      await useCredit(userId, "mix");
      await sql`INSERT INTO generations (user_id, type, result_url, prompt) VALUES (${userId}, 'mix', ${mixedUrl}, ${prompt})`;
      return NextResponse.json({ url: mixedUrl });
    }

    return NextResponse.json({ error: "Invalid type" }, { status: 400 });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
