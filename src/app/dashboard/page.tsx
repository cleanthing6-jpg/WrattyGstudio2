"use client";
import { useUser } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

const TIER_LIMITS: Record<string, { beats: number; covers: number; mixes: number; price: string }> = {
  free: { beats: 0, covers: 0, mixes: 0, price: "Free" },
  starter: { beats: 5, covers: 3, mixes: 0, price: "₦3,000" },
  pro: { beats: 12, covers: 6, mixes: 0, price: "₦7,000" },
  studio: { beats: 20, covers: 10, mixes: 1, price: "₦15,000" },
};

export default function Dashboard() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [usage, setUsage] = useState<any>(null);
      const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    if (!isSignedIn) return;
    fetch("/api/credits")
      .then((r) => r.json())
      .then((d) => setUsage(d))
      .catch(() => {});
  fetch("/api/history")
    .then((r) => r.json())
    .then((h) => setHistory(h.items || []))
    .catch(() => {});
  }, [isSignedIn]);

  if (!isLoaded) {
    return <div className="min-h-screen bg-[#faf9f4] grid place-items-center text-slate-500">Loading...</div>;
  }

  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-[#faf9f4] grid place-items-center text-center px-4">
        <div>
          <p className="text-slate-600">Please sign in to view your dashboard.</p>
          <Link href="/sign-in" className="mt-4 inline-block px-6 py-2.5 rounded-full bg-green-600 text-white font-bold">Sign in</Link>
        </div>
      </div>
    );
  }

  const firstName = user?.firstName || user?.username || "Creator";
  const plan = (usage && (usage.plan || "free")) || "free";
  const lim = TIER_LIMITS[plan] || TIER_LIMITS.free;
  const used = usage || {};
  const usedBeats = used.beats ?? used.used?.beats ?? 0;
  const usedCovers = used.covers ?? used.used?.covers ?? 0;
  const usedMixes = used.mixes ?? used.used?.mixes ?? 0;

  const statCards = [
    { icon: "🎵", label: "Beats", used: usedBeats, total: lim.beats, chip: "bg-green-100 text-green-700", bar: "bg-green-500", href: "/studio?type=beat" },
    { icon: "🖼️", label: "Album Covers", used: usedCovers, total: lim.covers, chip: "bg-yellow-100 text-yellow-700", bar: "bg-yellow-500", href: "/studio?type=cover" },
    { icon: "🎛️", label: "Mix & Master", used: usedMixes, total: lim.mixes, chip: "bg-red-100 text-red-700", bar: "bg-red-500", href: "/studio?type=mix" },
  ];

  return (
    <div className="min-h-screen bg-[#faf9f4] text-slate-900">
      <div className="h-1 bg-gradient-to-r from-green-500 via-yellow-400 to-red-500" />
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#faf9f4]/80 border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-green-500 to-yellow-500 grid place-items-center text-white font-black">W</span>
            <span className="font-extrabold tracking-tight text-lg">Wratty<span className="text-green-600">G</span>studio</span>
          </Link>
          <nav className="hidden md:flex items-center gap-7 text-sm text-slate-600">
            <Link href="/dashboard" className="font-bold text-green-700">Dashboard</Link>
            <Link href="/studio" className="hover:text-green-700">Studio</Link>
            <Link href="/pricing" className="hover:text-green-700">Pricing</Link>
          </nav>
          <Link href="/studio" className="px-4 py-2 rounded-full bg-green-600 text-white text-sm font-bold">Open Studio</Link>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
          <div>
            <h1 className="text-3xl font-black">Welcome back, {firstName} 👋</h1>
            <p className="text-slate-500 mt-1">Here is your studio at a glance.</p>
          </div>
          <span className="self-start sm:self-auto inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs font-bold text-slate-700 shadow-sm">
            <span className="flex gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /><span className="w-2 h-2 rounded-full bg-yellow-400" /><span className="w-2 h-2 rounded-full bg-red-500" /></span>
            {plan.toUpperCase()} PLAN
          </span>
        </div>
        <section className="mt-8 grid sm:grid-cols-3 gap-4">
          {statCards.map((c) => (
            <Link key={c.label} href={c.href} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md hover:border-green-400 transition">
              <div className="flex items-center justify-between">
                <div className={"w-11 h-11 rounded-xl grid place-items-center text-xl " + c.chip}>{c.icon}</div>
                <span className="text-xs font-bold text-slate-400">{c.used} / {c.total}</span>
              </div>
              <h3 className="mt-4 font-bold text-slate-900">{c.label}</h3>
              <div className="mt-3 h-2 rounded-full bg-slate-100 overflow-hidden">
                <div className={"h-full rounded-full " + c.bar} style={{ width: c.total > 0 ? Math.min(100, (c.used / c.total) * 100) + "%" : "0%" }} />
              </div>
              <p className="mt-2 text-xs text-slate-400">Tap to open →</p>
            </Link>
          ))}
        </section>

        <section className="mt-8 rounded-2xl bg-gradient-to-r from-green-600 to-yellow-500 p-6 text-white flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-xl font-black">Ready to make something great?</h2>
            <p className="text-white/85 text-sm mt-1">Generate a beat, design a cover, or mix your track.</p>
          </div>
          <Link href="/studio" className="px-6 py-3 rounded-full bg-white text-green-700 font-bold text-sm text-center hover:bg-green-50 transition">Go to Studio →</Link>
        </section>

        <section className="mt-8">
          <h2 className="text-lg font-bold mb-3">Need more? Upgrade your plan</h2>
          <div className="grid sm:grid-cols-3 gap-4">
            {Object.entries(TIER_LIMITS).filter(([k]) => k !== "free").map(([key, p]) => (
              <div key={key} className={"bg-white rounded-2xl p-5 border shadow-sm " + (key === "studio" ? "ring-2 ring-green-600 border-transparent" : "border-slate-200")}>
                <h3 className="font-bold capitalize">{key}</h3>
                <p className="mt-1 text-2xl font-black">{p.price}</p>
                <ul className="mt-3 space-y-1 text-xs text-slate-600">
                  <li>🎵 {p.beats} beats</li>
                  <li>🖼️ {p.covers} covers</li>
                  <li>🎛️ {p.mixes > 0 ? p.mixes + " pro mix & master" : "No pro mix included"}</li>
                </ul>
                <Link href="/pricing" className={"mt-4 block text-center px-4 py-2 rounded-full text-sm font-bold " + (key === "studio" ? "bg-green-600 text-white" : "border border-slate-300 text-slate-700")}>Choose {key}</Link>
              </div>
            ))}
          </div>
        </section>
      </main>
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-400 mt-8">
        <p className="font-bold text-sm text-slate-700">Wratty<span className="text-green-600">G</span>studio</p>
        <p className="mt-1">Made for African creators. © 2026</p>
      </footer>
    </div>
  );
}
