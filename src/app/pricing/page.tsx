"use client";

import { SignInButton, useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PLANS, MASTER_PLANS } from "@/lib/pricing";

const COLORS: Record<string, string> = {
  starter: "green", pro: "yellow", studio: "red",
  "master-single": "green", "master-ep": "yellow", "master-album": "red",
};

const FEATURES: Record<string, string[]> = {
  starter: ["1 finished mix + master", "Stem separation", "WAV + MP3 download"],
  pro: ["5 finished mixes + masters", "Priority processing", "Full FX & space controls"],
  studio: ["10 finished mixes + masters", "Fastest processing", "Commercial license"],
  "master-single": ["Master 1 finished stereo mix", "Loudness + tone + width", "WAV + MP3 download"],
  "master-ep": ["Master 5 finished stereo mixes", "Priority processing", "WAV + MP3 download"],
  "master-album": ["Master 10 finished stereo mixes", "Fastest processing", "Commercial license"],
};

const CTA: Record<string, string> = {
  starter: "Buy Single", pro: "Buy EP Pack", studio: "Buy Album",
  "master-single": "Master 1 Track", "master-ep": "Master 5 Tracks", "master-album": "Master 10 Tracks",
};

const naira = (n: number) => "\u20a6" + n.toLocaleString("en-NG");

const TIERS = [
  {
    id: "free",
    name: "Free",
    price: naira(0),
    period: "",
    features: ["1 watermarked 30s preview", "Hear it before you pay"],
    cta: "Start Free",
    color: "gray",
  },
  ...PLANS.filter((p) => p.id !== "free").map((p) => ({
    id: p.id,
    name: p.name,
    price: naira(p.ngn),
    period: "one-off \u00b7 credits never expire",
    features: FEATURES[p.id] ?? [p.tagline],
    cta: CTA[p.id] ?? "Buy",
    color: COLORS[p.id] ?? "green",
  })),
  ...MASTER_PLANS.map((p) => ({
    id: p.id,
    name: p.name + " \u00b7 mastering only",
    price: naira(p.ngn),
    period: "one-off \u00b7 credits never expire",
    features: FEATURES[p.id] ?? [p.tagline],
    cta: CTA[p.id] ?? "Buy",
    color: COLORS[p.id] ?? "green",
  })),
];

export default function Pricing() {
  const { user, isLoaded } = useUser();
  const router = useRouter();
  const [loadingTier, setLoadingTier] = useState<string | null>(null);

  const startPayment = async (tierId: string) => {
    if (tierId === "free") {
      router.push("/dashboard");
      return;
    }

    setLoadingTier(tierId);

    try {
      const res = await fetch("/api/paystack-init", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ tier: tierId }),
      });

      const data = await res.json();

      if (!res.ok || !data.url) {
        throw new Error(data.error || "Unable to start payment");
      }

      window.open(data.url, "_self");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Payment failed");
      setLoadingTier(null);
    }
  };

  return (
    <div className="min-h-screen px-4 py-12 max-w-5xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-black mb-3">Choose Your Plan</h1>
        <p className="text-gray-500">Start free. Upgrade when you&apos;re ready.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {TIERS.map((tier) => (
          <div
            key={tier.id}
            className={`bg-white rounded-2xl p-6 border ${
              tier.color === "green" ? "border-green-500" : "border-slate-200"
            }`}
          >
            {tier.color === "green" && (
              <div className="text-xs text-green-400 font-bold mb-2">
                MOST POPULAR
              </div>
            )}

            <h3 className="text-lg font-bold mb-1">{tier.name}</h3>

            <div className="text-3xl font-black mb-1">{tier.price}</div>

            {tier.period ? (
              <div className="text-gray-500 text-sm mb-4">{tier.period}</div>
            ) : (
              <div className="mb-4">&nbsp;</div>
            )}

            <ul className="space-y-2 mb-6">
              {tier.features.map((feature, index) => (
                <li
                  key={index}
                  className="text-sm text-gray-400 flex items-start gap-2"
                >
                  <span className="text-green-400 mt-0.5">✓</span>
                  {feature}
                </li>
              ))}
            </ul>

            {!isLoaded ? (
              <div className="w-full text-center text-gray-500 py-3">
                Loading...
              </div>
            ) : user ? (
              <button
                onClick={() => startPayment(tier.id)}
                disabled={loadingTier !== null}
                className="w-full bg-green-500/10 hover:bg-green-500/20 disabled:opacity-50 text-green-400 font-bold py-3 rounded-xl transition"
              >
                {loadingTier === tier.id ? "Connecting to Paystack..." : tier.cta}
              </button>
            ) : (
              <SignInButton mode="modal">
                <button className="w-full bg-green-500/10 hover:bg-green-500/20 text-green-400 font-bold py-3 rounded-xl transition">
                  {tier.cta}
                </button>
              </SignInButton>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
