import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

// Stems are already public (UploadThing) and the mixer fetches URLs directly,
// so staging is gone. Kept as a pass-through to preserve the old response shape.
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const url = String(body?.url || "");
  if (!/^https:\/\//.test(url)) {
    return NextResponse.json({ error: "url required" }, { status: 400 });
  }
  return NextResponse.json({ url });
}
