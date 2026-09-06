import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    tokenSet: !!process.env.UPLOADTHING_TOKEN,
    tokenLength: (process.env.UPLOADTHING_TOKEN || "").length,
    legacySecret: !!process.env.UPLOADTHING_SECRET,
    legacyAppId: !!process.env.UPLOADTHING_APP_ID,
  });
}
