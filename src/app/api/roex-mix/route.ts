import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const TONN = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";

async function tonnPost(path: string, body: unknown) {
  const res = await fetch(TONN + path, {
    method: "POST",
    headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function toRoEx(role: string, url: string, name: string) {
  const r = String(role || name || "").toLowerCase();
  if (r.includes("lead") || r.includes("vocal") || r.includes("main")) {
    return { trackURL: url, instrumentGroup: "VOCAL_GROUP", presenceSetting: "LEAD", panPreference: "CENTRE", reverbPreference: "LOW" };
  }
  if (r.includes("ad") || r.includes("adlib")) {
    return { trackURL: url, instrumentGroup: "BACKING_VOX_GROUP", presenceSetting: "BACKGROUND", panPreference: "NO_PREFERENCE", reverbPreference: "LOW" };
  }
  if (r.includes("back") || r.includes("harmony") || r.includes("chorus")) {
    return { trackURL: url, instrumentGroup: "BACKING_VOX_GROUP", presenceSetting: "NORMAL", panPreference: "NO_PREFERENCE", reverbPreference: "LOW" };
  }
  // Full instrumental/beat = backing track, NOT a drum stem
  return { trackURL: url, instrumentGroup: "BACKING_TRACK_GROUP", presenceSetting: "NORMAL", panPreference: "CENTRE", reverbPreference: "NONE" };
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { stems, style } = await req.json();
    if (!Array.isArray(stems) || stems.length < 2) {
      return NextResponse.json({ error: "RoEx needs at least 2 stems (e.g. lead vocal + beat)" }, { status: 400 });
    }

    // FREE: creates the 30s preview task — no credits charged
    const { ok, status, data } = await tonnPost("/mixpreview", {
      multitrackData: {
        trackData: stems.map((s) => toRoEx(s.role, s.url, s.name)),
        musicalStyle: typeof style === "string" && style.trim() ? style.trim().toUpperCase() : "AFROBEAT",
      },
    });
    if (!ok) return NextResponse.json({ error: "RoEx: " + JSON.stringify(data).slice(0, 300) }, { status: status || 502 });

    const taskId = data.multitrackTaskId || data.multitrack_task_id;
    if (!taskId) return NextResponse.json({ error: "RoEx: no task id — " + JSON.stringify(data).slice(0, 300) }, { status: 502 });

    return NextResponse.json({ taskId });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "RoEx failed" }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const taskId = req.nextUrl.searchParams.get("taskId");
    if (!taskId) return NextResponse.json({ error: "Missing taskId" }, { status: 400 });

    // Poll the free preview. retrieveFXSettings=false keeps it free.
    const { ok, status, data } = await tonnPost("/retrievepreviewmix", {
      multitrackData: { multitrackTaskId: taskId, retrieveFXSettings: false, returnStems: true },
    });

    if (ok) {
      const url = data?.previewMixTaskResults?.download_url_preview_mixed;
      if (url) return NextResponse.json({ status: "preview", url, raw: data });
      return NextResponse.json({ status: "processing" });
    }
    if (status === 202) return NextResponse.json({ status: "processing" });
    return NextResponse.json({ error: "RoEx: " + JSON.stringify(data).slice(0, 300) }, { status: status || 502 });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "RoEx poll failed" }, { status: 500 });
  }
}
