// Single source of truth for all pricing. Change numbers HERE only.
export type Region = "NG" | "INTL";

export type Plan = {
  id: string;        // MUST match your DB / Paystack tier id
  name: string;
  tracks: number;
  ngn: number;       // 0 = free
  usd: number;       // 0 = free
  tagline: string;
  popular?: boolean;
};

// Tier ids deliberately kept as free/starter/pro/studio so nothing
// in the backend, DB or Paystack needs renaming.
export const PLANS: Plan[] = [
  { id: "free",    name: "Free",     tracks: 0,  ngn: 0,     usd: 0,  tagline: "1 watermarked 30s preview" },
  { id: "starter", name: "Single",   tracks: 1,  ngn: 7500,  usd: 12, tagline: "1 finished mix + master" },
  { id: "pro",     name: "EP Pack",  tracks: 5,  ngn: 25000, usd: 45, tagline: "5 tracks, ~N5,000 each", popular: true },
  { id: "studio",  name: "Album",    tracks: 10, ngn: 45000, usd: 80, tagline: "10 tracks, best value" },
];

export const TIER_IDS = PLANS.map((p) => p.id);

export function regionFromCountry(country?: string | null): Region {
  return (country || "").toUpperCase() === "NG" ? "NG" : "INTL";
}

export function priceFor(plan: Plan, region: Region) {
  const amount = region === "NG" ? plan.ngn : plan.usd;
  const currency = region === "NG" ? "NGN" : "USD";
  const display = amount === 0
    ? "Free"
    : region === "NG"
      ? "\u20a6" + amount.toLocaleString("en-NG")
      : "$" + amount;
  return { amount, currency, display };
}

export function plansFor(region: Region) {
  return PLANS.map((p) => ({ ...p, price: priceFor(p, region) }));
}
