"use client";
import { useUser } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

const TIER_LIMITS: Record<string, { beats: number; covers: number; mixes: number; price: number; label: string }> = {
  free: { beats: 0, covers: 1, mixes: 0, price: 0, label: "FREE" },
  starter: { beats: 5, covers: 3, mixes: 3, price: 3000, label: "STARTER" },
  pro: { beats: 10, covers: 7, mixes: 10, price: 7000, label: "PRO" },
  studio: { beats: 30, covers: 20, mixes: 30, price: 14000, label: "STUDIO" },
};

export default function Dashboard() {
  const { user } = useUser();
  type Credits = {
  tier: string;
  beats_used: number;
  covers_used: number;
  mixes_used: number;
};

const [credits, setCredits] = useState<Credits | null>(null);

  useEffect(() => {
    fetch("/api/credits").then(r => r.json()).then(setCredits).catch(() => {});
  }, []);

  if (!user) return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading...</div>;

  const tier = credits?.tier || "free";
  const limits = TIER_LIMITS[tier];

  return (
    <div className="min-h-screen px-4 py-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-1">Welcome back, {user.firstName || "Creator"}</h1>
        <p className="text-gray-500">Your music studio dashboard</p>
      </div>

      {/* Current Plan */}
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl p-6 mb-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <span className="text-gray-400">Current Plan</span>
          <span className="text-green-400 font-bold text-lg">{limits.label}</span>
        </div>
        {tier === "free" && (
          <Link href="/pricing" className="block w-full text-center bg-green-500 hover:bg-green-400 text-black font-bold py-3 rounded-xl transition">
            Upgrade Plan →
          </Link>
        )}
        {tier !== "free" && (
          <div className="text-sm text-gray-500">Your plan renews monthly. Manage in Settings.</div>
        )}
      </div>

      {/* Credits */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <div className="text-gray-400 text-sm mb-1">Beats Generated</div>
          <div className="text-2xl font-bold mb-3">{credits?.beats_used || 0} / {limits.beats}</div>
          <Link href="/studio?type=beat" className="inline-block bg-green-500/10 text-green-400 hover:bg-green-500/20 font-semibold py-2 px-4 rounded-lg text-sm transition">
            Generate Beat →
          </Link>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <div className="text-gray-400 text-sm mb-1">Album Covers</div>
          <div className="text-2xl font-bold mb-3">{credits?.covers_used || 0} / {limits.covers}</div>
          <Link href="/studio?type=cover" className="inline-block bg-green-500/10 text-green-400 hover:bg-green-500/20 font-semibold py-2 px-4 rounded-lg text-sm transition">
            Create Cover →
          </Link>
        </div>
        <div className="bg-gray-900 rounded-2xl p-5 border border-gray-800">
          <div className="text-gray-400 text-sm mb-1">Mix & Master</div>
          <div className="text-2xl font-bold mb-3">{credits?.mixes_used || 0} / {limits.mixes}</div>
          <Link href="/studio?type=mix" className="inline-block bg-green-500/10 text-green-400 hover:bg-green-500/20 font-semibold py-2 px-4 rounded-lg text-sm transition">
            Upload & Mix →
          </Link>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-lg font-bold mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Link href="/studio?type=beat" className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-xl p-4 flex items-center gap-4 transition">
            <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center text-2xl">🎵</div>
            <div>
              <div className="font-semibold">Generate a Beat</div>
              <div className="text-gray-500 text-sm">Describe your beat, AI creates it</div>
            </div>
          </Link>
          <Link href="/studio?type=cover" className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-xl p-4 flex items-center gap-4 transition">
            <div className="w-12 h-12 rounded-xl bg-pink-500/20 flex items-center justify-center text-2xl">🎨</div>
            <div>
              <div className="font-semibold">Design Album Cover</div>
              <div className="text-gray-500 text-sm">Upload references or describe it</div>
            </div>
          </Link>
          <Link href="/studio?type=mix" className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-xl p-4 flex items-center gap-4 transition">
            <div className="w-12 h-12 rounded-xl bg-blue-500/20 flex items-center justify-center text-2xl">🎛️</div>
            <div>
              <div className="font-semibold">Mix & Master</div>
              <div className="text-gray-500 text-sm">Upload stems or rough recording</div>
            </div>
          </Link>
          <Link href="/studio?type=mix" className="bg-gray-900 hover:bg-gray-800 border border-gray-800 rounded-xl p-4 flex items-center gap-4 transition">
            <div className="w-12 h-12 rounded-xl bg-orange-500/20 flex items-center justify-center text-2xl">✂️</div>
            <div>
              <div className="font-semibold">Split Stems</div>
              <div className="text-gray-500 text-sm">Separate vocals, drums, bass</div>
            </div>
          </Link>
        </div>
      </div>

      {/* History */}
      <Link href="/history" className="text-gray-500 hover:text-white transition text-sm">
        View History →
      </Link>
    </div>
  );
}
