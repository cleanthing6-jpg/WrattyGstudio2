import { NextResponse } from "next/server";
import { validateApiKey } from "@/lib/apiAuth";

export async function GET(req: Request) {
  const auth = await validateApiKey(req);
  
  if (auth.error || !auth.client) {
    return NextResponse.json(
      { error: auth.error || "Invalid API Key" }, 
      { status: auth.status || 401 }
    );
  }

  return NextResponse.json({
    status: "active",
    credits_remaining: auth.client.credits,
    company_name: auth.client.name || "Developer",
    message: auth.client.credits <= 50 ? "Low balance. Please top up soon." : "Balance is healthy."
  });
}
