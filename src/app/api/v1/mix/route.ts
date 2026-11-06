import { NextResponse } from "next/server";
import { validateApiKey, deductCredit } from "@/lib/apiAuth";

export async function POST(req: Request) {
  const auth = await validateApiKey(req);
  
  // TypeScript strict fix: Ensure client exists before proceeding
  if (auth.error || !auth.client) {
    return NextResponse.json(
      { error: auth.error || "Invalid API Key" }, 
      { status: auth.status || 401 }
    );
  }

  try {
    const body = await req.json();
    const { stems, preset = "afrobeats", loudness = "HIGH" } = body;

    if (!Array.isArray(stems) || stems.length === 0) {
      return NextResponse.json({ error: "stems[] array is required" }, { status: 400 });
    }

    const modalUrl = process.env.MIX_API_URL || "https://wrattyg--wratty-mix-api.modal.run";
    const secret = process.env.FX_INTERNAL_SECRET || "";

    const response = await fetch(modalUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + secret,
      },
      body: JSON.stringify({
        stems,
        preset,
        loudness,
        maxSeconds: 300, 
      }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to start mix");

    // Safe to use auth.client here because we checked it above
    await deductCredit(auth.client.apiKey);

    return NextResponse.json({
      success: true,
      jobId: data.job,
      message: "Mix started successfully. Poll the status endpoint for updates."
    });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
