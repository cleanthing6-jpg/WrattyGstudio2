import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  try {
    const hash = req.nextUrl.searchParams.get("hash");
    if (!hash) return NextResponse.json({ error: "Missing hash" }, { status: 400 });

    let d: any = await (await fetch("https://mvsep.com/api/separation/get-remote?hash=" + encodeURIComponent(hash))).json();

    if (d.success && d.status === "done" && d.data && d.data.link) {
      d = await (await fetch(d.data.link)).json();
    } else if (!d.success && d.status === "not_found") {
      d = await (await fetch("https://mvsep.com/api/separation/get?hash=" + encodeURIComponent(hash))).json();
    }

    return NextResponse.json(d);
  } catch (e: any) {
    return NextResponse.json({ error: e.message || "Status check failed" }, { status: 500 });
  }
}
