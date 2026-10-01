import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";
import { STUDIO_KNOWLEDGE } from "@/lib/studioKnowledge";

export const runtime = "nodejs";
export const maxDuration = 30;

const has = (t: string, ...w: string[]) => w.some((x) => t.includes(x));
const word = (t: string, w: string) => new RegExp("\\b" + w + "\\b").test(t);

// Try newest first; fall through on 404/deprecated so a model rename
// never breaks the assistant.
const MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"];

async function askGemini(question: string): Promise<string> {
  const key = process.env.GEMINI_API_KEY || "";
  if (!key) return "";
  for (const model of MODELS) {
    try {
      const r = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models/" +
          model + ":generateContent?key=" + key,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            system_instruction: { parts: [{ text: STUDIO_KNOWLEDGE }] },
            contents: [{ role: "user", parts: [{ text: question }] }],
            generationConfig: { temperature: 0.4, maxOutputTokens: 500 },
          }),
          signal: AbortSignal.timeout(20000),
        }
      );
      if (!r.ok) continue;
      const d: any = await r.json().catch(() => null);
      const text = (d?.candidates?.[0]?.content?.parts || [])
        .map((p: any) => p.text || "").join("").trim();
      if (text) return text;
    } catch {
      // try the next model
    }
  }
  return "";
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => ({}));
  const raw = String(body?.prompt || "");
  const t = raw.toLowerCase();
  if (!t.trim()) return NextResponse.json({ error: "prompt required" }, { status: 400 });

  // ---- mix controls (unchanged contract) ----
  let preset = "afrobeats";
  if (has(t, "amapiano", "log drum", "electronic")) preset = "amapiano";
  else if (word(t, "rap") || has(t, "hip hop", "hiphop", "trap", "drill")) preset = "rap";
  else if (has(t, "reggae", "dancehall", "rnb", "r&b", "slow jam")) preset = "rnb";
  else if (word(t, "pop") || has(t, "top 40", "chart topper")) preset = "pop";
  else if (has(t, "acoustic", "rock", "indie")) preset = "neutral";

  let loudness = "MEDIUM";
  if (has(t, "loud", "tiktok", "club", "aggressive", "banger", "punchy", "radio-ready", "radio ready"))
    loudness = "HIGH";
  else if (has(t, "quiet", "dynamic", "gentle", "soft", "background"))
    loudness = "LOW";

  const less = has(t, "less reverb", "no reverb", "dry", "intimate", "tight");
  const more = !less && has(t, "more reverb", "wet", "spacious", "dreamy", "atmospheric", "lush", "reverb", "delay", "space");

  // ---- grounded answer (new) ----
  // Defaults ON. Set includeAnswer:false to skip Gemini entirely.
  const wantAnswer = body?.includeAnswer !== false;
  let answer = "";
  if (wantAnswer) {
    try {
      answer = await askGemini(raw);
    } catch {
      answer = "";
    }
  }

  return NextResponse.json({
    preset,
    loudness,
    plate_db: more ? -12 : less ? -20 : -18,
    slap_db: more ? -14 : less ? -20 : -16,
    reason: preset + " / " + loudness + (more ? " / more space" : less ? " / drier" : ""),
    ...(answer ? { answer } : {}),
  });
}
