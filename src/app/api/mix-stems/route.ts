import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    { error: "Stem separation is disabled. Please upload your raw stems." },
    { status: 403 }
  );
}
