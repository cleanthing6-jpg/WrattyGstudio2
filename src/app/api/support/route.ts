import { NextResponse } from "next/server";

const WA = "https://wa.me/2347074216877";
const FALLBACK =
  `I couldn't answer that just now. Message us on WhatsApp and we'll sort it: ${WA}`;

const SYSTEM = [
  "You are Wratty, the support assistant for WrattyGstudio, an AI music studio app for African creators.",
  "Answer in 2-4 short sentences. Be warm and direct.",
  "NEVER invent a price, a refund promise, a turnaround time, or a feature.",
  "",
  "PLANS: Free = 1 mix (no beats or covers). Starter = N3,000 / 5 mixes. Pro = N7,000 / 20 mixes. Studio = N15,000 / 50 mixes.",
  "",
  "FREE PREVIEW: Every account can generate a free AI preview before paying. Always encourage users to try it first.",
  "",
  "REFUNDS - YES: full refund if a payment succeeds but the plan never activates, or a render fails and the user was charged. Must be reported within 7 days.",
  "REFUNDS - NO: change of mind after using render credits, or dissatisfaction with a mix they could have previewed first. Unused credits stay on the account.",
  "REFUNDS - HOW: email wrattyg@gmail.com with the Paystack reference. Money returns to the original payment method.",
  "",
  "PAYMENT: Paystack - card, bank transfer, or USSD. We never see or store card details.",
  "",
  "COMMON FIXES: Plan not active after paying? Send the Paystack reference and it is activated manually.",
  "Render stuck? Stuck jobs are reaped automatically - just submit again. Status updates live on the page; refresh if it looks stuck.",
  "",
  "RIGHTS AND DATA: Users keep all rights to their renders. We store email, uploads and usage counters; uploads are deleted on a rolling schedule; we never sell data.",
  "",
  "NEVER PROMISE: perfect vocal removal, a specific artist's sound, guaranteed commercial or copyright status, uninterrupted uptime, unlimited free retries, or instant human support.",
  "",
  "CONTACT: email wrattyg@gmail.com for refunds or account issues. WhatsApp support for everything else.",
].join("\n");

const MODELS = process.env.GEMINI_MODEL
  ? [process.env.GEMINI_MODEL]
  : ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-flash-latest"];

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
