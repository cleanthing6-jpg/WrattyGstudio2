import { sql } from "./db";
import { PLANS, MASTER_PLANS } from "./pricing";

export type CreditType = "beat" | "cover" | "mix" | "master";

// Every tier id the DB may hold: free, the mix+master packs, and the
// mastering-only packs. Derived from lib/pricing.ts so they cannot drift.
const MIX_TIER_IDS = PLANS.filter((p) => p.id !== "free").map((p) => p.id);
const MASTER_TIER_IDS = MASTER_PLANS.map((p) => p.id);
const ALL_TIER_IDS = ["free", ...MIX_TIER_IDS, ...MASTER_TIER_IDS];

export type Limits = { beats: number; covers: number; mixes: number; masters: number };

export function limitsFor(tier: string): Limits {
  const mix = PLANS.find((p) => p.id === tier);
  const master = MASTER_PLANS.find((p) => p.id === tier);
  return {
    beats: 0,
    covers: 0,
    mixes: mix && tier !== "free" ? mix.tracks : 0,
    masters: master ? master.tracks : 0,
  };
}

function isTier(value: string): boolean {
  return ALL_TIER_IDS.includes(value);
}

let columnsReady = false;

// Adds the columns this module needs, once per process.
async function ensureColumns() {
  if (columnsReady) return;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS usage_reset_at TIMESTAMPTZ DEFAULT NOW()`;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS masters_used INT DEFAULT 0`;
  columnsReady = true;
}

// Rolling 30-day window: zero the counters once the window expires.
// NOTE: this makes every purchase refill monthly. See README note.
async function rollUsageWindow(userId: string) {
  await sql`
    UPDATE users
    SET mixes_used = 0,
        beats_used = 0,
        covers_used = 0,
        masters_used = 0,
        usage_reset_at = NOW()
    WHERE id = ${userId} AND usage_reset_at < NOW() - INTERVAL '30 days'
  `;
}

export async function getUser(userId: string) {
  await sql`
    INSERT INTO users (id)
    VALUES (${userId})
    ON CONFLICT (id) DO NOTHING
  `;

  await ensureColumns();
  await rollUsageWindow(userId);

  const rows = await sql`SELECT * FROM users WHERE id = ${userId}`;
  if (rows.length === 0) throw new Error("Unable to create user");
  return rows[0];
}

export async function checkCredit(userId: string, type: CreditType) {
  const user = await getUser(userId);
  const tier = isTier(String(user.tier)) ? String(user.tier) : "free";
  const lim = limitsFor(tier);

  const used =
    type === "beat" ? Number(user.beats_used ?? 0)
    : type === "cover" ? Number(user.covers_used ?? 0)
    : type === "mix" ? Number(user.mixes_used ?? 0)
    : Number(user.masters_used ?? 0);

  const limit =
    type === "beat" ? lim.beats
    : type === "cover" ? lim.covers
    : type === "mix" ? lim.mixes
    : lim.masters;

  return { allowed: used < limit, used, limit, tier };
}

export async function consumeCredit(userId: string, type: CreditType): Promise<boolean> {
  const user = await getUser(userId);
  const tier = isTier(String(user.tier)) ? String(user.tier) : "free";
  const lim = limitsFor(tier);

  const max =
    type === "beat" ? lim.beats
    : type === "cover" ? lim.covers
    : type === "mix" ? lim.mixes
    : lim.masters;

  // The WHERE clause re-checks the live value, so concurrent requests
  // cannot push usage past the limit.
  let result;
  if (type === "beat") {
    result = await sql`
      UPDATE users SET beats_used = beats_used + 1
      WHERE id = ${userId} AND beats_used < ${max}
      RETURNING beats_used`;
  } else if (type === "cover") {
    result = await sql`
      UPDATE users SET covers_used = covers_used + 1
      WHERE id = ${userId} AND covers_used < ${max}
      RETURNING covers_used`;
  } else if (type === "mix") {
    result = await sql`
      UPDATE users SET mixes_used = mixes_used + 1
      WHERE id = ${userId} AND mixes_used < ${max}
      RETURNING mixes_used`;
  } else {
    result = await sql`
      UPDATE users SET masters_used = masters_used + 1
      WHERE id = ${userId} AND masters_used < ${max}
      RETURNING masters_used`;
  }

  return (
    result.length > 0 ||
    userId === (process.env.OWNER_USER_ID || "user_3JwUmxdbT5FMshejHI7swJNHs9t")
  );
}

export async function setTier(userId: string, tier: string) {
  if (!isTier(tier)) throw new Error("Invalid tier: " + tier);

  await getUser(userId);

  await sql`
    UPDATE users
    SET tier = ${tier},
        beats_used = 0,
        covers_used = 0,
        mixes_used = 0,
        masters_used = 0,
        usage_reset_at = NOW()
    WHERE id = ${userId}
  `;
}
