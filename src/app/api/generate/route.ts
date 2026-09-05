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
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
    const { type, prompt } = body;

    if (!isGenerationType(type)) {
      return NextResponse.json({ error: "Invalid generation type" }, { status: 400 });
    }

    if (type !== "mix" && (!prompt || typeof prompt !== "string" || !prompt.trim())) {
      return NextResponse.json({ error: "A prompt is required" }, { status: 400 });
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
      const ref = typeof body.reference === "string" ? body.reference.trim() : "";
      const promptText = prompt.trim() + ", professional music album cover, square artwork, vibrant colors, high detail, no watermark, no extra text, no unreadable letters";
      let imgBase64 = "";
      if (!ref) {
        const cfRes = await fetch(
          "https://api.cloudflare.com/client/v4/accounts/" + process.env.CLOUDFLARE_ACCOUNT_ID + "/ai/run/@cf/black-forest-labs/flux-1-schnell",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: "Bearer " + process.env.CLOUDFLARE_API_TOKEN,
            },
            body: JSON.stringify({ prompt: promptText }),
          }
        );
        const cfData = await cfRes.json();
        if (!cfRes.ok || !cfData.result || !cfData.result.image) {
          return NextResponse.json(
            { error: "Cloudflare: " + (cfData.errors?.[0]?.message || cfData.message || "image generation failed") },
            { status: 502 }
          );
        }
        imgBase64 = cfData.result.image;
      } else {
        const buf = Buffer.from(ref, "base64");
        const form = new FormData();
        form.append("prompt", "Recreate this reference image as a professional music album cover: " + prompt.trim() + ". Keep the subject and style of the reference image. Square artwork, vibrant, high detail, no watermark, no extra text, no unreadable letters");
        form.append("input_image_0", new Blob([buf], { type: "image/jpeg" }), "ref.jpg");
        form.append("steps", "20");
        form.append("width", "1024");
        form.append("height", "1024");
        const cfRes = await fetch(
          "https://api.cloudflare.com/client/v4/accounts/" + process.env.CLOUDFLARE_ACCOUNT_ID + "/ai/run/@cf/black-forest-labs/flux-2-klein-4b",
          {
            method: "POST",
            headers: { Authorization: "Bearer " + process.env.CLOUDFLARE_API_TOKEN },
            body: form,
          }
        );
        const cfData = await cfRes.json();
        if (!cfRes.ok || !cfData.result || !cfData.result.image) {
          return NextResponse.json(
            { error: "Cloudflare flux2: " + (cfData.errors?.[0]?.message || cfData.message || JSON.stringify(cfData).slice(0, 200)) },
            { status: 502 }
          );
        }
        imgBase64 = cfData.result.image;
      }
      const coverUrl = "data:image/jpeg;base64," + imgBase64;
      const consumed = await consumeCredit(userId, "cover");
      if (!consumed) {
        return NextResponse.json({ error: "No album cover credits remaining" }, { status: 403 });
      }
      await sql`
        INSERT INTO generations (user_id, type, result_url, prompt)
        VALUES (${userId}, 'cover', ${coverUrl}, ${prompt.trim()})
      `;
      return NextResponse.json({ url: coverUrl });
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

const targetDuration = Math.min(360, Math.max(10, Math.round(duration * 1.06)));
      const musicRes = await fetch(
        "https://api.musicapi.ai/api/v1/sonic/create",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${process.env.MUSICAPI_KEY}`,
          },
          body: JSON.stringify({
            custom_mode: false,
            mv: "sonic-v5",
            gpt_description_prompt: `${prompt.trim()}, strictly instrumental, no vocals, no singing, no voices, no lyrics, no choir, instrumental only`,
            title: "WrattyGstudio",
            tags: "afrobeats, amapiano, instrumental",
            make_instrumental: true,
            duration: targetDuration,
          }),
        }
      );

      const musicData = await musicRes.json();
      if (!musicRes.ok || !musicData.task_id) {
        return NextResponse.json(
          { error: "MusicAPI status " + musicRes.status + " body " + JSON.stringify(musicData).slice(0,300) },
          { status: 502 }
        );
      }

      const taskId = musicData.task_id;

      for (let i = 0; i < 60; i++) {
        await new Promise((resolve) => setTimeout(resolve, 5000));

        const poll = await fetch(
          `https://api.musicapi.ai/api/v1/sonic/task/${taskId}`,
          {
            headers: {
              Authorization: `Bearer ${process.env.MUSICAPI_KEY}`,
            },
          }
        );

        const pollData = await poll.json();

      if (pollData.code === 200 && pollData.data && pollData.data.length > 0) {
        const clips = (pollData.data || []).filter((d: any) => d.state === "succeeded");
        const allDone = (pollData.data || []).every((d: any) => d.state === "succeeded" || d.state === "failed" || d.state === "error");
        if (allDone && clips.length > 0) {
          const consumed = await consumeCredit(userId, "beat");
          if (!consumed) {
            return NextResponse.json({ error: "No beat credits remaining" }, { status: 403 });
          }
          const tracks: { url: string; label: string }[] = [];
          for (let ti = 0; ti < clips.length; ti++) {
            const c = clips[ti];
            await sql`
              INSERT INTO generations (user_id, type, result_url, prompt)
              VALUES (${userId}, 'beat', ${c.audio_url}, ${prompt.trim()})
            `;
            tracks.push({ url: c.audio_url, label: "Version " + (ti + 1) });
          }
          return NextResponse.json({ url: tracks[0].url, tracks });
        }
      }
        if (pollData.code !== 200 && pollData.message?.includes?.("failed")) {
          return NextResponse.json({ error: "Beat generation failed" }, { status: 502 });
        }
      }

      return NextResponse.json({ error: "Beat generation timed out" }, { status: 504 });
    }

    return NextResponse.json(
      { error: "Mix processing is not connected yet. Please use the Mix & Master page when the processing engine is enabled." },
      { status: 501 }
    );
  } catch (error: unknown) {
    console.error("Generation error:", error);
    const message = error instanceof Error ? error.message : "Generation failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
