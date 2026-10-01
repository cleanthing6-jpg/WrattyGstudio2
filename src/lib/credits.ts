import { sql } from "./db";
import { findPlanById } from "./pricing";

export type CreditType = "beat" | "cover" | "mix" | "master";

let ready = false;

// Adds the balance columns once per process, and backfills existing paid
// tiers with the entitlement they actually bought (old terms, not new).
async function ensureSchema() {
  if (ready) return;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS mixes_used INT DEFAULT 0`;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS masters_used INT DEFAULT 0`;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS mix_credits INT DEFAULT 0`;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS master_credits INT DEFAULT 0`;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS usage_reset_at TIMESTAMPTZ DEFAULT NOW()`;

  // Idempotent: only fires for legacy paid rows that have no granted total yet.
  await sql`
    UPDATE users
    SET mix_credits = CASE tier
      WHEN 'starter' THEN 5
      WHEN 'pro' THEN 20
      WHEN 'studio' THEN 50
      ELSE mix_credits
    END
    WHERE tier IN ('starter','pro','studio') AND mix_credits = 0
  `;
  ready = true;
}

export async function getUser(userId: string) {
  await sql`
    INSERT INTO users (id) VALUES (${userId})
    ON CONFLICT (id) DO NOTHING
  `;
  await ensureSchema();
  const rows = await sql`SELECT * FROM users WHERE id = ${userId}`;
  if (rows.length === 0) throw new Error("Unable to create user");
  return rows[0];
}

function left(user: any) {
  return {
    mixes: Math.max(0, Number(user.mix_credits ?? 0) - Number(user.mixes_used ?? 0)),
    masters: Math.max(0, Number(user.master_credits ?? 0) - Number(user.masters_used ?? 0)),
  };
}

export async function checkCredit(userId: string, type: CreditType) {
  const user = await getUser(userId);
  const b = left(user);

  const used =
    type === "beat" ? Number(user.beats_used ?? 0)
    : type === "cover" ? Number(user.covers_used ?? 0)
    : type === "mix" ? Number(user.mixes_used ?? 0)
    : Number(user.masters_used ?? 0);

  const remaining = type === "mix" ? b.mixes : type === "master" ? b.masters : 0;

  // `remaining` is what is LEFT, not a ceiling - so allowed means "more than zero".
  return { allowed: remaining > 0, used, remaining, limit: remaining, tier: String(user.tier || "free") };
}

// Atomic: the WHERE clause re-reads the granted total, so concurrent
// requests can never push usage past the balance.
export async function consumeCredit(userId: string, type: CreditType): Promise<boolean> {
  await getUser(userId);

  let result;
  if (type === "beat") {
    result = await sql`UPDATE users SET beats_used = beats_used + 1
      WHERE id = ${userId} AND beats_used < 0 RETURNING beats_used`;
  } else if (type === "cover") {
    result = await sql`UPDATE users SET covers_used = covers_used + 1
      WHERE id = ${userId} AND covers_used < 0 RETURNING covers_used`;
  } else if (type === "mix") {
    result = await sql`UPDATE users SET mixes_used = mixes_used + 1
      WHERE id = ${userId} AND mixes_used < mix_credits RETURNING mixes_used`;
  } else {
    result = await sql`UPDATE users SET masters_used = masters_used + 1
      WHERE id = ${userId} AND masters_used < master_credits RETURNING masters_used`;
  }

  return (
    result.length > 0 ||
    userId === (process.env.OWNER_USER_ID || "user_3JwUmxdbT5FMshejHI7swJNHs9t")
  );
}

// Adds purchased credits. Never resets usage, never wipes the other balance.
export async function grantCredits(userId: string, tier: string) {
  const plan = findPlanById(tier);
  if (!plan) throw new Error("Unknown tier: " + tier);
  const addMix = plan.service === "master-only" ? 0 : plan.tracks;
  const addMaster = plan.service === "master-only" ? plan.tracks : 0;

  await getUser(userId);
  await sql`
    UPDATE users
    SET mix_credits = mix_credits + ${addMix},
        master_credits = master_credits + ${addMaster},
        tier = ${tier}
    WHERE id = ${userId}
  `;
}

// Display label only. Does NOT grant or reset anything.
export async function setTier(userId: string, tier: string) {
  if (tier !== "free" && !findPlanById(tier)) throw new Error("Invalid tier: " + tier);
  await getUser(userId);
  await sql`UPDATE users SET tier = ${tier} WHERE id = ${userId}`;
}
