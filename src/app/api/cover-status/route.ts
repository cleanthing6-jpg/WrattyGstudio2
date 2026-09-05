import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { consumeCredit } from "@/lib/credits";
import { sql } from "@/lib/db";

export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const jobId = req.nextUrl.searchParams.get("jobId") || "";
    const prompt = (req.nextUrl.searchParams.get("prompt") || "Album cover").slice(0, 500);
    if (!jobId) return NextResponse.json({ error: "Missing jobId" }, { status: 400 });
    const chk = await fetch("https://aihorde.net/api/v2/generate/check/" + jobId);
    const chkData = await chk.json();
    if (chkData.faulted) {
      return NextResponse.json({ error: "AI Horde job failed, please retry" }, { status: 502 });
    }
    if (!chkData.done || !(chkData.finished > 0)) {
      return NextResponse.json({ done: false });
    }
    const st = await fetch("https://aihorde.net/api/v2/generate/status/" + jobId);
    const stData = await st.json();
    const gen = stData.generations?.[0];
    if (!gen || !gen.img) {
      return NextResponse.json({ error: "AI Horde returned no image" }, { status: 502 });
    }
    const coverUrl = gen.img.startsWith("http") ? gen.img : "data:image/webp;base64," + gen.img;
    const consumed = await consumeCredit(userId, "cover");
    if (!consumed) {
      return NextResponse.json({ error: "No album cover credits remaining" }, { status: 403 });
    }
    await sql`
      INSERT INTO generations (user_id, type, result_url, prompt)
      VALUES (${userId}, 'cover', ${coverUrl}, ${prompt})
    `;
    return NextResponse.json({ done: true, url: coverUrl });
  } catch (error: unknown) {
    console.error("Cover status error:", error);
    return NextResponse.json({ error: error instanceof Error ? error.message : "Cover status failed" }, { status: 500 });
  }
}
