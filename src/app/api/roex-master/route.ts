import { NextResponse } from "next/server";

const BASE = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";

export async function POST(req: Request) {
  try {
    const { url, style = "AFROBEAT", loudness = "HIGH" } = await req.json();
    if (!url) return NextResponse.json({ error: "Missing track url" }, { status: 400 });

    const shapes = [
      { trackData: [{ trackURL: url }], musicalStyle: style, desiredLoudness: loudness },
      { trackData: { trackURL: url }, musicalStyle: style, desiredLoudness: loudness },
    ];

    let data: any = {};
    let status = 502;
    for (const body of shapes) {
      const r = await fetch(BASE + "/masteringpreview", {
        method: "POST",
        headers: { "x-api-key": KEY, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      status = r.status;
      data = await r.json().catch(() => ({}));
      if (r.ok) break;
      if (!/JSON format not valid|required/i.test(JSON.stringify(data || {}))) break;
    }

    const taskId = data && (data.mastering_task_id || data.masteringTaskId || data.taskId || data.task_id);
    if (!taskId) return NextResponse.json({ error: "RoEx: " + JSON.stringify(data).slice(0, 300) }, { status: status || 502 });
    return NextResponse.json({ taskId });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Master preview failed" }, { status: 500 });
  }
}

export async function GET(req: Request) {
  try {
    const id = new URL(req.url).searchParams.get("taskId");
    if (!id) return NextResponse.json({ error: "Missing taskId" }, { status: 400 });

    const s = await fetch(BASE + "/masteringstatus/" + id, { headers: { "x-api-key": KEY } });
    const sd: any = await s.json().catch(() => ({}));
    if (!s.ok) return NextResponse.json({ error: "RoEx: " + JSON.stringify(sd).slice(0, 300) }, { status: s.status || 502 });

    const td = sd.mastering_task_data || sd;
    const state = td.state || td.status || "";
    const masterUrl = td.download_url_mastered || td.download_url || "";

    return NextResponse.json({ status: state, state: state, masterUrl: masterUrl, url: masterUrl });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Master status failed" }, { status: 500 });
  }
}
