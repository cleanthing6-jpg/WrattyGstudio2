import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    { error: "Stem separation is currently disabled. Please upload your raw stems (Beat, Lead, Vocals) for the best quality." },
    { status: 403 }
  );
}
