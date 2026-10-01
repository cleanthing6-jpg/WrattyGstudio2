import { NextResponse } from "next/server";
import { STUDIO_KNOWLEDGE } from "@/lib/studioKnowledge";

export const runtime = "nodejs";
export const maxDuration = 30;

const WA = "https://wa.me/2347074216877";
const FALLBACK =
  `I couldn't answer that just now. Message us on WhatsApp and we'll sort it: ${WA}`;

const SYSTEM = [
  STUDIO_KNOWLEDGE,
  "",
  "## International prices (USD)",
  "Single $12, EP Pack $45, Album $80. Master Single $8, Master EP $30, Master Album $52.",
  "",
  "## Refunds - use these exact rules, never invent others",
  "YES: full refund if a payment succeeded but the plan never activated, or a render failed and the user was actually charged.",
  "NO: change of mind after using render credits, or dissatisfaction with a mix they could have previewed free first. Unused credits stay on the account and never expire.",
  "HOW: email wrattyg@gmail.com with the Paystack reference. Money returns to the original payment method.",
  "",
  "## Rights and data",
  "Users keep all rights to their renders. We store email, uploads and usage counters; uploads are deleted on a rolling schedule; we never sell data.",
  "",
  "## Never promise",
  "Perfect vocal removal, a specific artist's sound, guaranteed commercial or copyright clearance, uninterrupted uptime, unlimited free retries, or instant human support.",
  "",
  "## Contact",
  "Email wrattyg@gmail.com for refunds and account issues. WhatsApp for everything else.",
].join("\n");

const API = "https://generativelanguage.googleapis.com/v1beta";
const PREFERRED = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"];

// Models the key can actually call. Cached per warm instance.
let cachedModels: string[] | null = null;

async function availableModels(key: string): Promise<string[]> {
  if (cachedModels) return cachedModels;
  try {
    const r = await fetch(API + "/models", {
      headers: { "x-goog-api-key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const d: any = await r.json().catch(() => ({}));
    // Text-only chat models. TTS/image/transcribe/omni reject a TEXT request
    // (HTTP 400) or burn a separate quota (HTTP 429).
    const BAD = /tts|image|transcribe|lyria|nano-banana|embedding|aqa|omni|gemma/i;
    const all = (d?.models ?? [])
      .filter((m: any) => (m.supportedGenerationMethods ?? []).includes("generateContent"))
      .map((m: any) => String(m.name).replace("models/", ""))
      .filter((m: string) => m.startsWith("gemini-") && !BAD.test(m));
    if (all.length) cachedModels = all;
    return all;
  } catch {
    return [];
  }
}

// Order: GEMINI_MODEL (only if it exists), then preferred, then the rest.
async function candidates(key: string): Promise<string[]> {
  const env = (process.env.GEMINI_MODEL || "").trim();
  const avail = await availableModels(key);
  const out: string[] = [];
  const push = (m: string) => {
    if (!m || out.includes(m)) return;
    if (avail.length && !avail.includes(m)) return; // ignore bogus env name
    out.push(m);
  };
  push(env);
  PREFERRED.forEach(push);
  avail.forEach(push);
  return out.slice(0, 6);
}

type Try = { ok: true; text: string; model: string } | { ok: false; err: string };

async function generate(key: string, model: string, message: string): Promise<Try> {
  try {
    const r = await fetch(API + "/models/" + model + ":generateContent", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: SYSTEM }] },
        contents: [{ role: "user", parts: [{ text: message }] }],
        generationConfig: { temperature: 0.4, maxOutputTokens: 400 },
      }),
      signal: AbortSignal.timeout(25000),
    });
    const raw = await r.text();
    if (!r.ok) return { ok: false, err: model + " HTTP " + r.status + ": " + raw.slice(0, 180) };
    let d: any = {};
    try { d = JSON.parse(raw); } catch {}
    const text = (d?.candidates?.[0]?.content?.parts ?? [])
      .map((p: any) => p?.text ?? "").join("").trim();
    if (!text) return { ok: false, err: model + " returned no text: " + raw.slice(0, 180) };
    return { ok: true, text, model };
  } catch (e: any) {
    return { ok: false, err: model + " threw: " + (e?.name || "") + " " + (e?.message || "") };
  }
}

export async function POST(req: Request) {
  let message = "";
  try {
    const body = await req.json();
    message = String(body?.message ?? "").slice(0, 1000).trim();
  } catch {}

  if (!message) {
    return NextResponse.json({ answer: "Ask me anything about renders, plans, uploads or refunds." });
  }

  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    console.error("[support] GEMINI_API_KEY is not set");
    return NextResponse.json({ answer: FALLBACK, debug: "GEMINI_API_KEY not set" });
  }

  const list = await candidates(key);
  const errors: string[] = [];

  for (const model of list) {
    const r = await generate(key, model, message);
    if (r.ok) {
      console.log("[support] ok via " + r.model);
      return NextResponse.json({ answer: r.text, model: r.model });
    }
    errors.push(r.err);
    console.error("[support] " + r.err);
  }

  return NextResponse.json({
    answer: FALLBACK,
    debug: errors.length ? errors.join(" | ") : "no candidate models available",
  });
}

export async function GET() {
  const key = process.env.GEMINI_API_KEY;
  if (!key) return NextResponse.json({ error: "GEMINI_API_KEY not set" }, { status: 500 });
  const avail = await availableModels(key);
  const list = await candidates(key);
  return NextResponse.json({
    keyPresent: true,
    envModel: process.env.GEMINI_MODEL || null,
    availableCount: avail.length,
    willTry: list,
  });
}
