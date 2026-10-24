// src/app/api/tune/[id]/route.ts
import { NextResponse } from "next/server";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> | { id: string } }) {
  const { id } = await ctx.params;
  const r = await fetch(`${process.env.MODAL_TUNE_STATUS_URL}?job_id=${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) return NextResponse.json({ status: "error" }, { status: 502 });
  return NextResponse.json(await r.json());
}
