import { NextResponse } from "next/server";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const statusUrl = (
    process.env.MODAL_TUNE_STATUS_URL ||
    "https://wrattyg--wratty-autotune-status.us-east.modal.run"
  ).replace(/\/+$/, "");
  const r = await fetch(`${statusUrl}?job_id=${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) return NextResponse.json({ status: "error" }, { status: 502 });
  return NextResponse.json(await r.json());
}
