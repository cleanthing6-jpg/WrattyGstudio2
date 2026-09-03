"use client";
import { useUser } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";
const TIER_LIMITS: Record<string, { beats: number; covers: number; mixes: number; price: number }> = {
  free: { beats: 0, covers: 1, mixes: 0, price: 0 },
  starter: { beats: 5, covers: 3, mixes: 3, price: 3000 },
  pro: { beats: 10, covers: 7, mixes: 10, price: 7000 },
  studio: { beats: 30, covers: 20, mixes: 30, price: 14000 },
};
export default function Dashboard() {
  const { user } = useUser();
  const [data, setData] = useState<any>(null);
  useEffect(() => { if (user) fetch("/api/credits").then(r => r.json()).then(setData); }, [user]);
  if (!user) return <div className="min-h-screen flex items-center justify-center"><p className="text-gray-400">Sign in first</p></div>;
  if (!data) return <div className="min-h-screen flex items-center justify-center"><p className="text-gray-400">Loading...</p></div>;
  const limits = TIER_LIMITS[data.tier] || TIER_LIMITS.free;
  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
      <p className="text-gray-400 mb-6">Welcome back, {user.firstName || "Creator"}</p>
      <div className="bg-gray-900 rounded-xl p-6 mb-6">
        <h2 className="text-xl font-semibold mb-2">Current Plan: <span className="text-green-400 uppercase">{data.tier}</span></h2>
        {data.tier === "free" && (
          <div className="mt-4 flex flex-wrap gap-3">
            {["starter","pro","studio"].map(t => (
              <button key={t} onClick={async () => { const res = await fetch("/api/paystack-init", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tier: t }) }); const d = await res.json(); if (d.url) window.location.href = d.url; }} className="bg-green-500 hover:bg-green-600 text-black font-bold py-2 px-6 rounded-full text-sm capitalize">{t} — ₦{TIER_LIMITS[t].price.toLocaleString()}</button>
            ))}
          </div>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {[{ label: "Beats", used: data.beats_used, limit: limits.beats, href: "/studio?type=beat" },
          { label: "Covers", used: data.covers_used, limit: limits.covers, href: "/studio?type=cover" },
          { label: "Mixes", used: data.mixes_used, limit: limits.mixes, href: "/studio?type=mix" }].map(c => (
          <div key={c.label} className="bg-gray-900 rounded-xl p-5">
            <p className="text-gray-400 text-sm mb-1">{c.label}</p>
            <p className="text-2xl font-bold">{c.used} / {c.limit}</p>
            <Link href={c.href} className="mt-3 inline-block text-green-400 text-sm hover:underline">Create →</Link>
          </div>
        ))}
      </div>
      <Link href="/history" className="text-gray-400 hover:text-white">View History →</Link>
    </div>
  );
}
