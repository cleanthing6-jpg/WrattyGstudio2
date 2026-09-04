import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const formData = await req.formData();
    const file = formData.get("file") as File | null;
    const type = (formData.get("type") as string) || "automix";
    if (!file) return NextResponse.json({ error: "No audio file uploaded" }, { status: 400 });

    const allowed = ["stems", "automix", "master"];
    if (!allowed.includes(type)) {
      return NextResponse.json({ error: "Unknown processing type: " + type }, { status: 400 });
    }

    const sizeMB = Math.max(1, Math.round(file.size / (1024 * 1024)));
    return NextResponse.json({
      ok: true,
      type,
      filename: file.name,
      sizeMB,
      url: "",
      message: "Track received. Engine not connected yet - free engine keys will activate processing."
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
