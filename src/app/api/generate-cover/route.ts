import { NextRequest, NextResponse } from "next/server";

type GeminiResponse = {
  candidates?: Array<{
    content?: {
      parts?: Array<{
        text?: string;
      }>;
    };
  }>;
  error?: {
    message?: string;
  };
};

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const prompt = String(formData.get("prompt") || "").trim();

    if (!prompt) {
      return NextResponse.json(
        { error: "A cover prompt is required" },
        { status: 400 }
      );
    }

    const response = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=" +
        process.env.GEMINI_API_KEY,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          contents: [
            {
              parts: [
                {
                  text:
                    "Create a professional album cover concept. " +
                    prompt +
                    ". Square 1:1 format, high quality.",
                },
              ],
            },
          ],
        }),
      }
    );

    const data = (await response.json()) as GeminiResponse;

    if (!response.ok) {
      return NextResponse.json(
        {
          error:
            data.error?.message || "Cover generation service failed",
        },
        { status: 502 }
      );
    }

    const text = data.candidates?.[0]?.content?.parts?.[0]?.text;

    return NextResponse.json({
      url: text || "Generated cover concept created",
    });
  } catch (error: unknown) {
    console.error("Cover generation error:", error);

    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Cover generation failed",
      },
      { status: 500 }
    );
  }
}
