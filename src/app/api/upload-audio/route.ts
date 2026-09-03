import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;
    if (!file) return NextResponse.json({ error: "No file" }, { status: 400 });
    const buffer = Buffer.from(await file.arrayBuffer());
    const base64 = buffer.toString("base64");
    return NextResponse.json({ url: `data:audio/${file.name.split(".").pop()};base64,${base64}` });
  } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 500 }); }
}
