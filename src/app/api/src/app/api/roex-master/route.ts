import { NextResponse } from "next/server";

const BASE = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";

export async function POST(req: Request) {
  try {
    const { url, style = "AFROBEAT", loudness = "MEDIUM" } = await req.json();
    if (!url) return NextResponse.json({ error: "Missing track url" }, { status: 400 });

    const r = await fetch(`${BASE}/masteringpreview`, {
      method: "POST",
      headers: { "x-api-key": KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        masteringData: {
          trackURL: url,
          musicalStyle: style,
          desiredLoudness: loudness,
          sampleRate: "44100",
        },
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return NextResponse.json({ error: "RoEx: " + JSON.stringify(data).slice(0, 300) }, { status: r.status || 502 });

    const taskId = data.masteringTaskId || data.mastering_task_id || data.taskId;
    if (!taskId) return NextResponse.json({ error: "RoEx: no mastering task id" }, { status: 502 });
    return NextResponse.json({ taskId });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Master preview failed" }, { status: 500 });
  }
}

export async function GET(req: Request) {
  try {
    const id = new URL(req.url).searchParams.get("taskId");
    if (!id) return NextResponse.json({ error: "Missing taskId" }, { status: 400 });

    const s = await fetch(`${BASE}/masteringstatus/${id}`, { headers: { "x-api-key": KEY } });
    const sd = await s.json().catch(() => ({}));
    if (!s.ok) return NextResponse.json({ error: "RoEx: " + JSON.stringify(sd).slice(0, 300) }, { status: s.status || 502 });
    return NextResponse.json({ status: sd.status, previewUrl: sd.preview_url || sd.previewUrl || "" });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Master status failed" }, { status: 500 });
  }
}
