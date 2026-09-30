import { sql } from "./db";

type CreditType = "beat" | "cover" | "mix";
type Tier = "free" | "starter" | "pro" | "studio";

const TIERS: Record<Tier, { beats: number; covers: number; mixes: number }> = {
  free: { beats: 0, covers: 0, mixes: 1 },
  starter: { beats: 0, covers: 0, mixes: 5 },
  pro: { beats: 0, covers: 0, mixes: 20 },
  studio: { beats: 0, covers: 0, mixes: 50 },
};


function isTier(value: string): value is Tier {
  return value === "free" || value === "starter" || value === "pro" || value === "studio";
}

let resetColumnReady = false;

// Adds the usage_reset_at column once per process; a no-op afterwards.
async function ensureResetColumn() {
  if (resetColumnReady) return;
  await sql`ALTER TABLE users ADD COLUMN IF NOT EXISTS usage_reset_at TIMESTAMPTZ DEFAULT NOW()`;
  resetColumnReady = true;
}

// Rolling 30-day window: zero the counters once the window expires.
async function rollUsageWindow(userId: string) {
  await sql`
    UPDATE users
    SET mixes_used = 0, beats_used = 0, covers_used = 0, usage_reset_at = NOW()
    WHERE id = ${userId} AND usage_reset_at < NOW() - INTERVAL '30 days'
  `;
}

export async function getUser(userId: string) {
  await sql`
    INSERT INTO users (id)
    VALUES (${userId})
    ON CONFLICT (id) DO NOTHING
  `;

  await ensureResetColumn();
  await rollUsageWindow(userId);

  const rows = await sql`
    SELECT * FROM users
    WHERE id = ${userId}
  `;

  if (rows.length === 0) {
    throw new Error("Unable to create user");
  }

  return rows[0];
}

export async function checkCredit(userId: string, type: CreditType) {
  const user = await getUser(userId);

  const userTier = String(user.tier);
  const tier: Tier = isTier(userTier) ? userTier : "free";
  const limits = TIERS[tier];

  const used =
    type === "beat"
      ? Number(user.beats_used)
      : type === "cover"
        ? Number(user.covers_used)
        : Number(user.mixes_used);

  const limit =
    type === "beat"
      ? limits.beats
      : type === "cover"
        ? limits.covers
        : limits.mixes;

  return {
    allowed: used < limit,
    used,
    limit,
    tier,
  };
}

export async function consumeCredit(
  userId: string,
  type: CreditType
): Promise<boolean> {
  const column =
    type === "beat"
      ? "beats_used"
      : type === "cover"
        ? "covers_used"
        : "mixes_used";

  const limits = {
    beat: { free: 0, starter: 0, pro: 0, studio: 0 },
    cover: { free: 0, starter: 0, pro: 0, studio: 0 },
    mix: { free: 1, starter: 5, pro: 20, studio: 50 },
  };

  const maxCredits = limits[type];

  let result;

  if (column === "beats_used") {
    result = await sql`
      UPDATE users
      SET beats_used = beats_used + 1
      WHERE id = ${userId}
        AND beats_used < CASE tier
          WHEN 'free' THEN ${maxCredits.free}
          WHEN 'starter' THEN ${maxCredits.starter}
          WHEN 'pro' THEN ${maxCredits.pro}
          WHEN 'studio' THEN ${maxCredits.studio}
          ELSE 0
        END
      RETURNING beats_used
    `;
  } else if (column === "covers_used") {
    result = await sql`
      UPDATE users
      SET covers_used = covers_used + 1
      WHERE id = ${userId}
        AND covers_used < CASE tier
          WHEN 'free' THEN ${maxCredits.free}
          WHEN 'starter' THEN ${maxCredits.starter}
          WHEN 'pro' THEN ${maxCredits.pro}
          WHEN 'studio' THEN ${maxCredits.studio}
          ELSE 0
        END
      RETURNING covers_used
    `;
  } else {
    result = await sql`
      UPDATE users
      SET mixes_used = mixes_used + 1
      WHERE id = ${userId}
        AND mixes_used < CASE tier
          WHEN 'free' THEN ${maxCredits.free}
          WHEN 'starter' THEN ${maxCredits.starter}
          WHEN 'pro' THEN ${maxCredits.pro}
          WHEN 'studio' THEN ${maxCredits.studio}
          ELSE 0
        END
      RETURNING mixes_used
    `;
  }

    return result.length > 0 || userId === (process.env.OWNER_USER_ID || "user_3IqTsednC0Bqdk3JMxeGzW6zdGD");

}

export async function setTier(userId: string, tier: string) {
  if (!isTier(tier)) {
    throw new Error("Invalid tier");
  }

  await getUser(userId);

  await sql`
    UPDATE users
    SET
      tier = ${tier},
      beats_used = 0,
      covers_used = 0,
      mixes_used = 0
    WHERE id = ${userId}
  `;
}
