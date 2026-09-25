import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const has = (t: string, ...w: string[]) => w.some((x) => t.includes(x));
const word = (t: string, w: string) => new RegExp("\\b" + w + "\\b").test(t);

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const t = String(body?.prompt || "").toLowerCase();
  if (!t.trim()) return NextResponse.json({ error: "prompt required" }, { status: 400 });

  let preset = "afrobeats";
  if (has(t, "amapiano", "log drum")) preset = "amapiano";
  else if (word(t, "rap") || has(t, "hip hop", "hiphop", "trap", "drill")) preset = "rap";
  else if (has(t, "reggae", "dancehall", "rnb", "slow jam")) preset = "rnb";
  else if (word(t, "pop") || has(t, "top 40", "chart topper")) preset = "pop";
  else if (has(t, "acoustic", "rock", "indie")) preset = "neutral";

  let loudness = "MEDIUM";
  if (has(t, "loud", "tiktok", "club", "aggressive", "banger", "punchy", "radio-ready", "radio ready"))
    loudness = "HIGH";
  else if (has(t, "quiet", "dynamic", "gentle", "soft", "background"))
    loudness = "LOW";

  const less = has(t, "less reverb", "no reverb", "dry", "intimate", "tight");
  const more = !less && has(t, "more reverb", "wet", "spacious", "dreamy", "atmospheric", "lush", "reverb", "delay", "space");

  return NextResponse.json({
    preset,
    loudness,
    plate_db: more ? -12 : less ? -20 : -18,
    slap_db: more ? -14 : less ? -20 : -16,
    reason: preset + " / " + loudness + (more ? " / more space" : less ? " / drier" : ""),
  });
}
