import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

const WA = "https://wa.me/2347074216877";
const LIMIT = 10;          // messages per user per minute
const WINDOW_MS = 60_000;
const MAX_MESSAGE = 1000;

// Per-process only: resets on restart/deploy. Adequate for one Render process
// (WEB_CONCURRENCY=1); multiple instances would need a shared limiter.
const hits = new Map<string, { start: number; count: number }>();

const SYSTEM = `
You are WrattyGstudio's support assistant. Use ONLY these facts:
- Free AI previews are 30 seconds; free users get up to 10 preview requests per rolling 24 hours.
- Pro gives 20 mix & master renders; Studio gives 50.
- Refunds: report within 7 days if a payment succeeded but the plan did not activate, or a render failed and you were charged. No refund for change of mind after using credits.
- Upload: sign in, open Studio, upload your stems, wait for the upload to finish, then start the mix.
- Render status appears live in the app.
- Payments are handled by Paystack; we never see card details.

Never invent prices, plan terms or limits, and never promise a refund.
If you are unsure, or the issue is payment, refund, or account-specific, set escalate=true.
Reply with JSON only: {"answer":"...","escalate":true|false}
`;

function fallback() {
  return {
    answer: `I couldn't answer that just now. Message us on WhatsApp and we'll sort it: ${WA}`,
    escalate: true,
  };
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Sign in first" }, { status: 401 });

  let body: any;
  try {
    const text = await req.text();
    if (text.length > 5000) return NextResponse.json({ error: "Request too large" }, { status: 413 });
    body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const message = body?.message;
  if (typeof message !== "string" || !message.trim() || message.length > MAX_MESSAGE) {
    return NextResponse.json({ error: `Message must be 1-${MAX_MESSAGE} characters` }, { status: 400 });
  }

  const now = Date.now();
  const hit = hits.get(userId);
  if (!hit || now - hit.start >= WINDOW_MS) hits.set(userId, { start: now, count: 1 });
  else if (hit.count >= LIMIT) return NextResponse.json({ error: "Too many messages - try again in a minute" }, { status: 429 });
  else hit.count++;

  if (hits.size > 10000) {
    for (const [id, h] of hits) if (now - h.start >= WINDOW_MS) hits.delete(id);
  }

  const key = process.env.GEMINI_API_KEY;
  if (!key) return NextResponse.json(fallback());

  try {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${encodeURIComponent(key)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(12000),
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYSTEM }] },
          contents: [{ parts: [{ text: message.trim() }] }],
          generationConfig: { responseMimeType: "application/json", maxOutputTokens: 250 },
        }),
      }
    );
    if (!r.ok) return NextResponse.json(fallback());

    const data = await r.json();
    const raw = data?.candidates?.[0]?.content?.parts?.[0]?.text;
    const parsed = JSON.parse(raw);
    const answer = typeof parsed?.answer === "string" ? parsed.answer : fallback().answer;
    const escalate = parsed?.escalate === true;
    return NextResponse.json({
      answer: escalate ? `${answer}\n\nChat with us: ${WA}` : answer,
      escalate,
    });
  } catch {
    return NextResponse.json(fallback());
  }
}
