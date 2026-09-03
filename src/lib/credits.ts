import { sql } from "./db";
const TIERS: Record<string, { beats: number; covers: number; mixes: number }> = {
  free: { beats: 0, covers: 1, mixes: 0 },
  starter: { beats: 5, covers: 3, mixes: 3 },
  pro: { beats: 10, covers: 7, mixes: 10 },
  studio: { beats: 30, covers: 20, mixes: 30 },
};
export async function getUser(userId: string) {
  const rows = await sql`SELECT * FROM users WHERE id = ${userId}`;
  if (rows.length === 0) {
    await sql`INSERT INTO users (id) VALUES (${userId})`;
    return { tier: "free", beats_used: 0, covers_used: 0, mixes_used: 0 };
  }
  return rows[0];
}
export async function checkCredit(userId: string, type: string) {
  const user = await getUser(userId);
  const tier = TIERS[user.tier] || TIERS.free;
  const used = type === "beat" ? user.beats_used : type === "cover" ? user.covers_used : user.mixes_used;
  const limit = type === "beat" ? tier.beats : type === "cover" ? tier.covers : tier.mixes;
  return { allowed: used < limit, used, limit, tier: user.tier };
}
export async function useCredit(userId: string, type: string) {
  if (type === "beat") await sql`UPDATE users SET beats_used = beats_used + 1 WHERE id = ${userId}`;
  else if (type === "cover") await sql`UPDATE users SET covers_used = covers_used + 1 WHERE id = ${userId}`;
  else await sql`UPDATE users SET mixes_used = mixes_used + 1 WHERE id = ${userId}`;
}
export async function setTier(userId: string, tier: string) {
  await sql`UPDATE users SET tier = ${tier}, beats_used = 0, covers_used = 0, mixes_used = 0 WHERE id = ${userId}`;
}
