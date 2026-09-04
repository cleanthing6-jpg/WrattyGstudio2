import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { checkCredit, useCredit } from "@/lib/credits";
import { sql } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const body = await req.json();
    const { type, prompt } = body;

    if (type === "cover") {
      const ok = await checkCredit(userId, "cover");
      if (!ok) return NextResponse.json({ error: "No credits left for album covers" }, { status: 403 });

      const apiKey = process.env.GEMINI_API_KEY;
      const models = ["gemini-3.1-flash-image", "gemini-2.5-flash-image"];

      for (const model of models) {
        try {
          const response = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                contents: [{
                  parts: [{
                    text: `Create a professional music album cover. Subject: ${prompt}. Vibrant, high-quality, suitable for an African music release. No text unless specified.`
                  }]
                }],
                generationConfig: { responseModalities: ["IMAGE"] }
              })
            }
          );
          const data = await response.json();

          const part = data?.candidates?.[0]?.content?.parts?.find((p: any) => p.inlineData);
          if (part?.inlineData?.data) {
            const imageUrl = `data:${part.inlineData.mimeType};base64,${part.inlineData.data}`;
            await useCredit(userId, "cover");
            await sql`INSERT INTO generations (user_id, type, result_url, prompt) VALUES (${userId}, 'cover', ${imageUrl.substring(0, 200)}, ${prompt})`;
            return NextResponse.json({ url: imageUrl });
          }
        } catch { /* try next model */ }
      }

      return NextResponse.json({ error: "Image generation failed. Check that GEMINI_API_KEY is valid and has image access." }, { status: 500 });
    }

    if (type === "beat") {
      const ok = await checkCredit(userId, "beat");
      if (!ok) return NextResponse.json({ error: "No credits left for beats" }, { status: 403 });

      const aimlRes = await fetch("https://api.aimlapi.com/v2/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${process.env.AIMLAPI_KEY}` },
        body: JSON.stringify({ model: "minimax/music-01", prompt, duration: body.duration || 180, return_all: false })
      });
      const aimlData = await aimlRes.json();

      if (aimlData.id) {
        for (let i = 0; i < 60; i++) {
          await new Promise(r => setTimeout(r, 5000));
          const poll = await fetch(`https://api.aimlapi.com/v2/generation/${aimlData.id}`, {
            headers: { "Authorization": `Bearer ${process.env.AIMLAPI_KEY}` }
          });
          const pd = await poll.json();
          if (pd.status === "completed" && pd.audio_url) {
            await useCredit(userId, "beat");
            await sql`INSERT INTO generations (user_id, type, result_url, prompt) VALUES (${userId}, 'beat', ${pd.audio_url}, ${prompt})`;
            return NextResponse.json({ url: pd.audio_url });
          }
          if (pd.status === "failed") return NextResponse.json({ error: "Beat generation failed" }, { status: 500 });
        }
        return NextResponse.json({ error: "Beat generation timed out" }, { status: 500 });
      }
      return NextResponse.json({ error: aimlData.message || "Beat generation failed" }, { status: 500 });
    }

    if (type === "mix") {
      const ok = await checkCredit(userId, "mix");
      if (!ok) return NextResponse.json({ error: "No credits left for mixing" }, { status: 403 });
      await useCredit(userId, "mix");
      return NextResponse.json({ url: body.audioUrl || "", message: "Mix processing initiated" });
    }

    return NextResponse.json({ error: "Unknown generation type" }, { status: 400 });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
