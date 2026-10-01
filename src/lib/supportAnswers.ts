// Answers built in CODE, never by the model. Prices here can never be
// truncated, reworded or invented by the AI.
export const PRICE_MIX =
  "Mix & Master: Single N7,500 (1 track), EP Pack N25,000 (5), Album N45,000 (10). International: $12, $45, $80. Previews are free and credits never expire.";

export const PRICE_MASTER =
  "Master only: Master Single N5,000 (1 stereo mix), Master EP N17,500 (5), Master Album N31,500 (10). International: $8, $30, $52.";

export const PRICE_ALL = PRICE_MIX + "\n\n" + PRICE_MASTER;

export const HANDOFF_REPLY =
  "No wahala - reach the team on WhatsApp at https://wa.me/2347074216877 and they'll take it from there.";

export const PAID_NO_CREDIT_REPLY =
  "Sorry about that. Please refresh the dashboard first - credits usually appear on their own. If they are still missing, email wrattyg@gmail.com with your Paystack reference and the team will fix it.";

export const REFUND_REPLY =
  "Refunds are handled by the team, not by me. Email wrattyg@gmail.com with your Paystack reference - if the plan never activated, or a render failed and you were charged, you get a full refund within 7 days.";

const PRICE_INTENT =
  /\b(price|prices|pricing|cost|costs|charge|charges|fee|fees|package|packages|packs?|rates?|how\s+much)\b/i;
const MASTER_ONLY = /\bmaster(ing)?[\s-]*only\b|\bjust\s+master/i;
const MIX_WORD = /\bmix(ing)?\b/i;
const HUMAN_INTENT =
  /\b(human|real\s+person|agent|support\s+team|speak\s+to|talk\s+to|chat\s+with)\b/i;
const PAID_NO_CREDIT_INTENT =
  /\b(paid|payed|payment|paystack)\b[\s\S]*\b(no|not|didn'?t|didnt|missing|haven'?t|havent|yet)\b[\s\S]*\b(credit|credits|plan|package|pack|balance|activ)/i;
const REFUND_INTENT = /\brefund|money\s+back|reverse(d)?\s+(the\s+)?(payment|charge)/i;

// Returns a fixed answer, or null to let Gemini handle it.
export function fixedAnswer(message: string): string | null {
  const t = message.toLowerCase();

  if (HUMAN_INTENT.test(t)) return HANDOFF_REPLY;
  if (PAID_NO_CREDIT_INTENT.test(t)) return PAID_NO_CREDIT_REPLY;
  if (REFUND_INTENT.test(t)) return REFUND_REPLY;

  if (PRICE_INTENT.test(t)) {
    const masterOnly = MASTER_ONLY.test(t);
    const wantsMix = MIX_WORD.test(t);
    if (masterOnly && !wantsMix) return PRICE_MASTER;
    if (wantsMix && !masterOnly) return PRICE_MIX;
    return PRICE_ALL;
  }

  return null;
}
