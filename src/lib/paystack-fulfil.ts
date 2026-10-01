import { sql } from "@/lib/db";
import { setTier } from "@/lib/credits";
import { findPlanById } from "@/lib/pricing";

// Derived from lib/pricing.ts - the single source of truth.
// Paystack amounts are in the smallest unit: kobo for NGN, cents for USD.
function expectedAmount(tier: string, currency: string): number | undefined {
  const plan = findPlanById(tier);
  if (!plan) return undefined;
  if (currency === "NGN") return plan.ngn * 100;
  if (currency === "USD") return plan.usd * 100;
  return undefined;
}

let _ready = false;
// Idempotent: creates the table, and adds `status` if it already exists.
async function ensureRefsTable() {
  if (_ready) return;
  await sql`CREATE TABLE IF NOT EXISTS paystack_refs (
    reference TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'granted',
    created_at TIMESTAMP DEFAULT NOW()
  )`;
  await sql`ALTER TABLE paystack_refs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'granted'`;
  // Self-heal: a crash mid-grant must not strand a paid reference forever.
  await sql`UPDATE paystack_refs SET status='pending'
            WHERE status='granting' AND created_at < NOW() - INTERVAL '10 minutes'`;
  _ready = true;
}

// Called by BOTH the browser callback and the webhook. Safe to call repeatedly.
export async function fulfilPaystackReference(reference: string) {
  await ensureRefsTable();

  const secret = process.env.PAYSTACK_SECRET_KEY;
  if (!secret) throw new Error("PAYSTACK_SECRET_KEY missing");

  const res = await fetch(
    `https://api.paystack.co/transaction/verify/${encodeURIComponent(reference)}`,
    { headers: { Authorization: `Bearer ${secret}` } }
  );
  const body = await res.json();
  const tx = body?.data;

  const userId = tx?.metadata?.userId;
  const tier = tx?.metadata?.tier;
  const currency = tx?.currency;
  const expected = expectedAmount(tier, currency);

  if (
    !res.ok ||
    body?.status !== true ||
    tx?.status !== "success" ||
    tx?.reference !== reference ||
    typeof userId !== "string" ||
    typeof tier !== "string" ||
    !expected ||
    tx?.amount !== expected
  ) {
    throw new Error("Payment verification failed");
  }

  // Atomic claim: exactly one caller (callback OR webhook) may grant.
  const claimed = (await sql`
    INSERT INTO paystack_refs (reference, user_id, tier, status)
    VALUES (${reference}, ${userId}, ${tier}, 'granting')
    ON CONFLICT (reference) DO UPDATE SET status = 'granting'
      WHERE paystack_refs.status NOT IN ('granted', 'granting')
    RETURNING reference
  `) as any[];
  if (!claimed.length) return "already_granted";

  try {
    await setTier(userId, tier);
  } catch (e) {
    // Release so a retry can grant, instead of stranding a paid reference.
    await sql`UPDATE paystack_refs SET status='pending'
              WHERE reference=${reference} AND status='granting'`;
    throw e;
  }

  await sql`UPDATE paystack_refs SET status='granted' WHERE reference=${reference}`;
  return "granted";
}
