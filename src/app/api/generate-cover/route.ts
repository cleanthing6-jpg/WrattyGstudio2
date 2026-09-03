import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const prompt = formData.get("prompt") as string;
    const image = formData.get("image") as File | null;
    let contents: any[] = [{ text: `Transform this into a professional album cover. ${prompt}. 1:1 square format, high quality.` }];
    if (image) {
      const buffer = Buffer.from(await image.arrayBuffer());
      const base64 = buffer.toString("base64");
      contents.unshift({ inline_data: { mime_type: image.type, data: base64 } });
    }
    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${process.env.GEMINI_API_KEY}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: contents }] }),
    });
    const data = await response.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
    return NextResponse.json({ url: text || "Generated cover prompt created" });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
