import { NextResponse } from "next/server";
import { validateApiKey, deductCredit } from "@/lib/apiAuth";

export async function POST(req: Request) {
  const auth = await validateApiKey(req);
  
  if (auth.error || !auth.client) {
    return NextResponse.json(
      { error: auth.error || "Invalid API Key" }, 
      { status: auth.status || 401 }
    );
  }

  try {
    const body = await req.json();
    const { 
      stems, 
      preset = "afrobeats", 
      loudness = "HIGH",
      mode = "mix" // "mix" for full stems, "master" for stereo
    } = body;

    if (!Array.isArray(stems) || stems.length === 0) {
      return NextResponse.json({ error: "stems[] array is required" }, { status: 400 });
    }

    const modalUrl = process.env.MIX_API_URL || "https://wrattyg--wratty-mix-api.modal.run";
    const secret = process.env.FX_INTERNAL_SECRET || "";

    // Send to Idan mix engine
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
        mode, // Pass the mode to the engine
        maxSeconds: 300, 
      }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to start mix");

    // Deduct credit based on mode
    // 1 Credit = Full Mix. 0.5 Credits = Master Only.
    const cost = mode === "master" ? 0.5 : 1.0;
    await deductCredit(auth.client.apiKey, cost);

    return NextResponse.json({
      success: true,
      jobId: data.job,
      mode: mode,
      message: "Job started successfully. Poll the status endpoint for updates."
    });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
