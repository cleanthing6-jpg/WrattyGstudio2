import { NextResponse } from "next/server";

export async function GET() {
  const t = process.env.UPLOADTHING_TOKEN || "";
  let parsed: any = null;
  let decodeError = "";
  try {
    parsed = JSON.parse(Buffer.from(t, "base64").toString("utf8"));
  } catch (e: any) {
    decodeError = e.message || "decode failed";
  }
  return NextResponse.json({
    tokenSet: !!t,
    tokenLength: t.length,
    decoded: parsed ? { apiKeyPrefix: String(parsed.apiKey || "").slice(0, 8), appId: parsed.appId, regions: parsed.regions } : null,
    decodeError,
  });
}
