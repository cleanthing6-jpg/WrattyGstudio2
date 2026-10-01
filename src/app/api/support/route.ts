import { NextResponse } from "next/server";
import { STUDIO_KNOWLEDGE } from "@/lib/studioKnowledge";

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

const MODELS = process.env.GEMINI_MODEL
  ? [process.env.GEMINI_MODEL]
  : ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"];

export async function POST(req: Request) {
  let message = "";
  try {
    const body = await req.json();
    message = String(body?.message ?? "").slice(0, 1000).trim();
  } catch {}

  if (!message) {
    return NextResponse.json({
      answer: "Ask me anything about renders, plans, uploads or refunds.",
    });
  }

  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    console.error("[support] GEMINI_API_KEY is not set");
    return NextResponse.json({ answer: FALLBACK });
  }

  for (const model of MODELS) {
    try {
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
          },
          body: JSON.stringify({
            systemInstruction: { parts: [{ text: SYSTEM }] },
            contents: [{ role: "user", parts: [{ text: message }] }],
            generationConfig: { temperature: 0.4, maxOutputTokens: 400 },
          }),
        }
      );

      const raw = await res.text();

      if (!res.ok) {
        console.error(`[support] ${model} HTTP ${res.status}: ${raw.slice(0, 300)}`);
        continue;
      }

      let data: any = {};
      try {
        data = JSON.parse(raw);
      } catch {}

      const parts = data?.candidates?.[0]?.content?.parts ?? [];
      const text = parts
        .map((p: any) => p?.text ?? "")
        .join("")
        .trim();

      if (!text) {
        console.error(`[support] ${model} returned no text: ${raw.slice(0, 300)}`);
        continue;
      }

      console.log(`[support] ok via ${model}`);
      return NextResponse.json({ answer: text });
    } catch (e: any) {
      console.error(`[support] ${model} threw:`, e?.name, e?.message);
    }
  }

  return NextResponse.json({ answer: FALLBACK });
}

export async function GET() {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    return NextResponse.json({ error: "GEMINI_API_KEY not set" }, { status: 500 });
  }
  try {
    const res = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models",
      { headers: { "x-goog-api-key": key } }
    );
    const raw = await res.text();
    let models: string[] = [];
    try {
      const d = JSON.parse(raw);
      models = (d.models ?? [])
        .filter((m: any) =>
          (m.supportedGenerationMethods ?? []).includes("generateContent")
        )
        .map((m: any) => String(m.name).replace("models/", ""));
    } catch {}
    return NextResponse.json({
      status: res.status,
      count: models.length,
      models,
      error: models.length ? undefined : raw.slice(0, 400),
    });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "failed" }, { status: 500 });
  }
}
