import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 60;

const TONN = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { url, name } = await req.json();
    if (typeof url !== "string" || url.length === 0) {
      return NextResponse.json({ error: "url required" }, { status: 400 });
    }

    const filename = String(name || "stem.wav");
    const lower = filename.toLowerCase();
    const contentType = lower.endsWith(".mp3")
      ? "audio/mpeg"
      : lower.endsWith(".flac")
        ? "audio/flac"
        : "audio/wav";

    const slotRes = await fetch(TONN + "/upload", {
      method: "POST",
      headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ filename, contentType }),
    });
    const slot = await slotRes.json().catch(() => ({}));
    if (!slotRes.ok) {
      console.log("[ROEX-UPLOAD] slot_failed=" + slotRes.status + " body=" + JSON.stringify(slot).slice(0, 300));
      return NextResponse.json(
        { error: "RoEx upload slot failed: " + JSON.stringify(slot).slice(0, 300) },
        { status: 502 }
      );
    }

    const signedUrl = slot.signed_url || slot.signedUrl || slot.upload_url || slot.uploadUrl || "";
    const readableUrl = slot.readable_url || slot.readableUrl || slot.url || "";

    if (!signedUrl) {
      console.log("[ROEX-UPLOAD] no_signed_url body=" + JSON.stringify(slot).slice(0, 300));
      return NextResponse.json(
        { error: "RoEx returned no signed_url: " + JSON.stringify(slot).slice(0, 300) },
        { status: 502 }
      );
    }

    const src = await fetch(url);
    if (!src.ok) {
      return NextResponse.json({ error: "Could not read source file: " + src.status }, { status: 502 });
    }
    const bytes = await src.arrayBuffer();

    const put = await fetch(signedUrl, {
      method: "PUT",
      headers: { "Content-Type": contentType },
      body: bytes,
    });
    if (!put.ok) {
      const t = await put.text().catch(() => "");
      console.log("[ROEX-UPLOAD] put_failed=" + put.status + " " + t.slice(0, 200));
      return NextResponse.json(
        { error: "Upload to RoEx failed: " + put.status + " " + t.slice(0, 200) },
        { status: 502 }
      );
    }

    const finalUrl = readableUrl || signedUrl.split("?")[0];
    console.log("[ROEX-UPLOAD] ok name=" + filename + " bytes=" + bytes.byteLength + " url=" + finalUrl.slice(0, 110));
    return NextResponse.json({ url: finalUrl, filename });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || "RoEx staging failed" }, { status: 500 });
  }
}
