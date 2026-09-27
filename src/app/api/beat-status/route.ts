import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BEAT_API = process.env.BEAT_API_URL || "";

// Proxies the Modal job status. The bearer secret stays server-side.
export async function GET(req: NextRequest) {
  try {
    const job = req.nextUrl.searchParams.get("job") || "";

    if (!job) {
      return NextResponse.json({ error: "job is required" }, { status: 400 });
    }
    if (!BEAT_API) {
      return NextResponse.json(
        { error: "beat engine not configured" },
        { status: 500 },
      );
    }

    const r = await fetch(`${BEAT_API}/?id=${encodeURIComponent(job)}`, {
      cache: "no-store",
    });
    const data = await r.json().catch(() => ({} as any));

    return NextResponse.json({
      status: data?.status || "none",
      ...(data?.url ? { url: data.url } : {}),
      ...(data?.error ? { error: data.error } : {}),
    });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Request failed" },
      { status: 500 },
    );
  }
}
