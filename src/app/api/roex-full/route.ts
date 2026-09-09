import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 60;

const TONN = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function tonnPost(path: string, body: unknown) {
  const res = await fetch(TONN + path, {
    method: "POST",
    headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { taskId, stems } = await req.json();
    if (!taskId || !Array.isArray(stems) || stems.length < 2) {
      return NextResponse.json({ error: "taskId + at least 2 stems required" }, { status: 400 });
    }

    // PAID (~250 credits). trackURL-only = engine uses its default DSP from the preview.
    const body = {
      applyAudioEffectsData: {
        multitrackTaskId: taskId,
        trackData: stems.map((s: any) => ({ trackURL: s.url })),
        returnStems: false,
      },
    };

    for (let i = 0; i < 12; i++) {
      const { ok, status, data } = await tonnPost("/retrievefinalmix", body);
      if (ok) {
        const url = data?.applyAudioEffectsResults?.download_url_mixed;
        if (url) return NextResponse.json({ status: "done", url });
      } else if (status === 400 || status === 401) {
        return NextResponse.json({ error: "RoEx: " + JSON.stringify(data).slice(0, 300) }, { status: status || 502 });
      }
      await sleep(5000);
    }
    return NextResponse.json({ error: "RoEx full mix timed out — try again in a minute" }, { status: 504 });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "RoEx full mix failed" }, { status: 500 });
  }
}
