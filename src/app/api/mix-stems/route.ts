import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const MVSEP_TOKEN = process.env.MVSEP_API_TOKEN || "";

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const ct = req.headers.get("content-type") || "";
    let form: FormData = new FormData();
    form.append("api_token", MVSEP_TOKEN);
    form.append("sep_type", "20");

    if (ct.includes("application/json")) {
      const body = await req.json();
      const audioUrl = typeof body.audioUrl === "string" ? body.audioUrl.trim() : "";
      if (!audioUrl) return NextResponse.json({ error: "Missing audio URL" }, { status: 400 });
      form.append("url", audioUrl);
    } else {
      const fd = await req.formData();
      const file = fd.get("file") as File | null;
      if (!file) return NextResponse.json({ error: "No audio file" }, { status: 400 });
      const buf = Buffer.from(await file.arrayBuffer());
      form.append("audiofile", new Blob([buf], { type: file.type || "audio/mpeg" }), file.name || "track.mp3");
    }

    const res = await fetch("https://mvsep.com/api/separation/create", { method: "POST", body: form });
    const data = await res.json();
    const hash = data?.data?.hash || data?.hash;

    if (!hash) {
      return NextResponse.json({ error: "MVSEP: " + JSON.stringify(data).slice(0, 300) }, { status: 502 });
    }

    return NextResponse.json({ taskId: hash });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || "Stem split failed" }, { status: 500 });
  }
}
