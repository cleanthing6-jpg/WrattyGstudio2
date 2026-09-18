import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;
    if (!file) return NextResponse.json({ error: "No file" }, { status: 400 });
    const buffer = Buffer.from(await file.arrayBuffer());
    const base64 = buffer.toString("base64");
    return NextResponse.json({ url: `data:audio/${file.name.split(".").pop()};base64,${base64}` });
  } catch (e: unknown) { return NextResponse.json({ error: e instanceof Error ? e.message : "Request failed" }, { status: 500 }); }
}
