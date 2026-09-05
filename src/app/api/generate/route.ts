import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { checkCredit, consumeCredit } from "@/lib/credits";
import { sql } from "@/lib/db";

type GenerationType = "beat" | "cover" | "mix";

function isGenerationType(value: unknown): value is GenerationType {
  return value === "beat" || value === "cover" || value === "mix";
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();

    if (!userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await req.json();
    const { type, prompt } = body;

    if (!isGenerationType(type)) {
      return NextResponse.json(
        { error: "Invalid generation type" },
        { status: 400 }
      );
    }

    if (type !== "mix" && (!prompt || typeof prompt !== "string" || !prompt.trim())) {
      return NextResponse.json(
        { error: "A prompt is required" },
        { status: 400 }
      );
    }

    const credit = await checkCredit(userId, type);

    if (!credit.allowed) {
      return NextResponse.json(
        {
          error: `No credits left for ${type === "cover" ? "album covers" : type === "beat" ? "beats" : "mixing"}`,
          tier: credit.tier,
          used: credit.used,
          limit: credit.limit,
        },
        { status: 403 }
      );
    }

    if (type === "cover") {
      const stylePrompt =
        "Professional music album cover. " +
        prompt.trim() +
        ". Vibrant, high quality, suitable for an African music release, square artwork, no watermark";

      const enc = encodeURIComponent(stylePrompt);

      const imgUrl =
        "https://image.pollinations.ai/prompt/" +
        enc +
        "?width=1024&height=1024&model=flux&nologo=true";

      const res = await fetch(imgUrl);

      if (!res.ok) {
        return NextResponse.json(
          { error: "Cover service busy, please retry in a few seconds" },
          { status: 502 }
        );
      }

      const consumed = await consumeCredit(userId, "cover");

      if (!consumed) {
        return NextResponse.json(
          { error: "No album cover credits remaining" },
          { status: 403 }
        );
      }

      await sql`
        INSERT INTO generations (user_id, type, result_url, prompt)
        VALUES (${userId}, 'cover', ${imgUrl}, ${prompt.trim()})
      `;

      return NextResponse.json({ url: imgUrl });
    }

    if (type === "beat") {
      const duration =
        typeof body.duration === "number"
          ? body.duration
          : Number(body.duration) || 180;

      if (!Number.isFinite(duration) || duration < 10 || duration > 600) {
        return NextResponse.json(
          { error: "Duration must be between 10 and 600 seconds" },
          { status: 400 }
        );
      }

      const aimlRes = await fetch(
        "https://api.aimlapi.com/v2/generation",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${process.env.MUSICAPI_KEY}`,
          },
          body: JSON.stringify({
            model: "minimax/music-01",
            prompt: prompt.trim(),
            duration,
            return_all: false,
          }),
        }
      );

      const aimlData = await aimlRes.json();

      if (!aimlRes.ok || !aimlData.id) {
        return NextResponse.json(
          {
            error:
              aimlData.message ||
              "Beat generation service is unavailable",
          },
          { status: 502 }
        );
      }

      for (let i = 0; i < 60; i++) {
        await new Promise((resolve) => setTimeout(resolve, 5000));

        const poll = await fetch(
          `https://api.aimlapi.com/v2/generation/${aimlData.id}`,
          {
            headers: {
              Authorization: `Bearer ${process.env.MUSICAPI_KEY}`,
            },
          }
        );

        const pollData = await poll.json();

        if (pollData.status === "completed" && pollData.audio_url) {
          const consumed = await consumeCredit(userId, "beat");

          if (!consumed) {
            return NextResponse.json(
              { error: "No beat credits remaining" },
              { status: 403 }
            );
          }

          await sql`
            INSERT INTO generations (user_id, type, result_url, prompt)
            VALUES (${userId}, 'beat', ${pollData.audio_url}, ${prompt.trim()})
          `;

          return NextResponse.json({
            url: pollData.audio_url,
          });
        }

        if (pollData.status === "failed") {
          return NextResponse.json(
            { error: "Beat generation failed" },
            { status: 502 }
          );
        }
      }

      return NextResponse.json(
        { error: "Beat generation timed out" },
        { status: 504 }
      );
    }

    return NextResponse.json(
      {
        error:
          "Mix processing is not connected yet. Please use the Mix & Master page when the processing engine is enabled.",
      },
      { status: 501 }
    );
  } catch (error: unknown) {
    console.error("Generation error:", error);

    const message =
      error instanceof Error
        ? error.message
        : "Generation failed";

    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}
