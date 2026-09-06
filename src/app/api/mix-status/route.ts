import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  try {
    const hash = req.nextUrl.searchParams.get("hash");
    if (!hash) return NextResponse.json({ error: "Missing hash" }, { status: 400 });

    let data: any = await (await fetch("https://mvsep.com/api/separation/get-remote?hash=" + encodeURIComponent(hash))).json();

    if (!data.success && data.status === "not_found") {
      data = await (await fetch("https://mvsep.com/api/separation/get?hash=" + encodeURIComponent(hash))).json();
    }

    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message || "Status check failed" }, { status: 500 });
  }
}
