import { sql } from "@/lib/db";
import { setTier } from "@/lib/credits";

const PRICES: Record<string, number> = {
  starter: 300000,
  pro: 700000,
  studio: 1400000,
};

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
  _ready = true;
}

// Called by BOTH the browser callback and the webhook. Safe to call repeatedly.
export async function fulfilPaystackReference(reference: string) {
  await ensureRefsTable();

  const done = (await sql`
    SELECT status FROM paystack_refs WHERE reference = ${reference} LIMIT 1
  `) as any[];
  if (done[0]?.status === "granted") return "already_granted";

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
  const expected = PRICES[tier];

  if (
    !res.ok ||
    body?.status !== true ||
    tx?.status !== "success" ||
    tx?.reference !== reference ||
    typeof userId !== "string" ||
    typeof tier !== "string" ||
    !expected ||
    tx?.amount !== expected ||
    tx?.currency !== "NGN"
  ) {
    throw new Error("Payment verification failed");
  }

  await setTier(userId, tier);

  await sql`
    INSERT INTO paystack_refs (reference, user_id, tier, status)
    VALUES (${reference}, ${userId}, ${tier}, 'granted')
    ON CONFLICT (reference) DO UPDATE SET status = 'granted'
  `;

  return "granted";
}
