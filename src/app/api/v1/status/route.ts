import { NextResponse } from "next/server";
import { validateApiKey } from "@/lib/apiAuth";

export async function GET(req: Request) {
  const auth = await validateApiKey(req);
  if (auth.error) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }

  const { searchParams } = new URL(req.url);
  const jobId = searchParams.get("id");

  if (!jobId) {
    return NextResponse.json({ error: "Missing job id" }, { status: 400 });
  }

  try {
    const modalUrl = process.env.MIX_API_URL || "https://wrattyg--wratty-mix-api.modal.run";
    
    const response = await fetch(modalUrl + "/?id=" + jobId, {
      headers: {
        "Authorization": "Bearer " + (process.env.FX_INTERNAL_SECRET || ""),
      },
    });

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
