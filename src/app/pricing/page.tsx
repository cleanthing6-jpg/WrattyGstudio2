"use client";
import { SignInButton, useUser } from "@clerk/nextjs";
import Link from "next/link";

const TIERS = [
  { name: "Free", price: "₦0", features: ["1 album cover", "Mix & master preview only", "No beat generation"], cta: "Start Free", color: "gray" },
  { name: "Starter", price: "₦3,000", period: "/month", features: ["5 beat generations", "3 album covers", "3 mix & master downloads", "Full-length beats"], cta: "Get Starter", color: "green" },
  { name: "Pro", price: "₦7,000", period: "/month", features: ["10 beat generations", "7 album covers", "10 mix & master downloads", "Priority processing"], cta: "Get Pro", color: "yellow" },
  { name: "Studio", price: "₦14,000", period: "/month", features: ["30 beat generations", "20 album covers", "30 mix & master downloads", "Fastest processing", "Commercial license"], cta: "Get Studio", color: "red" },
];

export default function Pricing() {
  const { user } = useUser();
  return (
    <div className="min-h-screen px-4 py-12 max-w-5xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-black mb-3">Choose Your Plan</h1>
        <p className="text-gray-500">Start free. Upgrade when you're ready.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {TIERS.map(tier => (
          <div key={tier.name} className={`bg-gray-900 rounded-2xl p-6 border ${tier.color === "green" ? "border-green-500" : "border-gray-800"}`}>
            {tier.color === "green" && <div className="text-xs text-green-400 font-bold mb-2">MOST POPULAR</div>}
            <h3 className="text-lg font-bold mb-1">{tier.name}</h3>
            <div className="text-3xl font-black mb-1">{tier.price}</div>
            {tier.period && <div className="text-gray-500 text-sm mb-4">{tier.period}</div>}
            {!tier.period && <div className="mb-4"></div>}
            <ul className="space-y-2 mb-6">
              {tier.features.map((f, i) => (
                <li key={i} className="text-sm text-gray-400 flex items-start gap-2">
                  <span className="text-green-400 mt-0.5">✓</span> {f}
                </li>
              ))}
            </ul>
            {user ? (
              <Link href="/dashboard" className="block text-center bg-green-500/10 hover:bg-green-500/20 text-green-400 font-bold py-3 rounded-xl transition">
                {tier.cta}
              </Link>
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
