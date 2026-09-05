"use client";
import { useUser } from "@clerk/nextjs";
import Link from "next/link";

const FEATURES = [
  { icon: "🎵", title: "AI Beat Generator", desc: "Describe a vibe - Afrobeats, Amapiano, Highlife - and get a full 2-3 minute track, not a loop.", chip: "bg-green-100" },
  { icon: "🖼️", title: "Album Covers", desc: "Upload reference images, describe the look, and get a release-ready cover in seconds.", chip: "bg-yellow-100" },
  { icon: "🎛️", title: "Mix & Master", desc: "Upload a rough phone recording and hear a professional mix and master of your own song.", chip: "bg-red-100" },
];

const PLANS = [
  { name: "Starter", price: "₦3,000", items: ["5 AI beats", "3 album covers"], hot: false },
  { name: "Pro", price: "₦7,000", items: ["12 AI beats", "6 album covers"], hot: false },
  { name: "Studio", price: "₦15,000", items: ["20 AI beats", "10 album covers", "1 pro mix & master"], hot: true },
];

export default function Home() {
  const { isLoaded, isSignedIn } = useUser();
  return (
    <div className="min-h-screen bg-[#faf9f4] text-slate-900 overflow-x-hidden">
      <div className="h-1 bg-gradient-to-r from-green-500 via-yellow-400 to-red-500" />
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#faf9f4]/80 border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-green-500 to-yellow-500 grid place-items-center text-white font-black">W</span>
            <span className="font-extrabold tracking-tight text-lg">Wratty<span className="text-green-600">G</span>studio</span>
          </Link>
          <nav className="hidden md:flex items-center gap-7 text-sm text-slate-600">
            <Link href="/studio">Studio</Link>
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/pricing">Pricing</Link>
          </nav>
          <div>
            {isLoaded && isSignedIn ? (
              <Link href="/studio" className="px-4 py-2 rounded-full bg-green-600 text-white text-sm font-bold">Open Studio</Link>
            ) : (
              <Link href="/sign-in" className="px-4 py-2 rounded-full bg-green-600 text-white text-sm font-bold">Get started</Link>
            )}
          </div>
        </div>
      </header>
      <main>
        <section className="max-w-6xl mx-auto px-4 pt-16 pb-10 text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs text-slate-600 shadow-sm">
            <span className="flex gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /><span className="w-2 h-2 rounded-full bg-yellow-400" /><span className="w-2 h-2 rounded-full bg-red-500" /></span>
            AI Music Studio for African sounds
          </span>
          <h1 className="mt-6 text-5xl md:text-7xl font-black tracking-tight leading-[1.02]">
            Upload. Automix.
            <br />
            <span className="bg-gradient-to-r from-green-600 via-yellow-500 to-red-500 bg-clip-text text-transparent">Master. Release.</span>
          </h1>
          <p className="mt-5 max-w-xl mx-auto text-slate-600 md:text-lg">Generate full beats, design album covers, and give your rough songs a professional mix and master - all from your phone, with AI doing the work.</p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            {isLoaded && isSignedIn ? (
              <Link href="/studio" className="px-7 py-3 rounded-full bg-green-600 text-white font-bold shadow-lg shadow-green-600/20">Go to Studio</Link>
            ) : (
              <Link href="/sign-in" className="px-7 py-3 rounded-full bg-green-600 text-white font-bold shadow-lg shadow-green-600/20">Start creating free</Link>
            )}
            <Link href="/pricing" className="px-7 py-3 rounded-full border border-slate-300 text-slate-700">See pricing</Link>
          </div>
        </section>
        <section className="max-w-6xl mx-auto px-4 py-12">
          <h2 className="text-center text-3xl font-extrabold">Everything in one studio</h2>
          <p className="text-center text-slate-500 mt-2 mb-8">Three tools. Zero studio gear.</p>
          <div className="grid md:grid-cols-3 gap-4">
            {FEATURES.map((f) => (
              <div key={f.title} className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
                <div className={"w-12 h-12 rounded-xl grid place-items-center text-2xl " + f.chip}>{f.icon}</div>
                <h3 className="mt-4 text-lg font-bold">{f.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{f.desc}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="max-w-6xl mx-auto px-4 py-12">
          <h2 className="text-center text-3xl font-extrabold">Simple pricing</h2>
          <p className="text-center text-slate-500 mt-2 mb-8">Hear your song professionally mixed for free before you pay.</p>
          <div className="grid md:grid-cols-3 gap-4 items-stretch">
            {PLANS.map((p) => (
              <div key={p.name} className={"relative bg-white rounded-2xl p-6 flex flex-col " + (p.hot ? "ring-2 ring-green-600 shadow-lg" : "border border-slate-200 shadow-sm")}>
                {p.hot && <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[11px] font-bold bg-green-600 text-white px-3 py-1 rounded-full">MOST POPULAR</span>}
                <h3 className="font-bold">{p.name}</h3>
                <p className="mt-3 text-3xl font-black">{p.price}<span className="text-sm font-normal text-slate-400"> / once</span></p>
                <ul className="mt-5 space-y-2 text-sm text-slate-600 flex-1">{p.items.map((it) => <li key={it} className="flex items-center gap-2"><span className="text-green-600 font-bold">✓</span>{it}</li>)}</ul>
                <Link href="/pricing" className={"mt-6 text-center px-4 py-2.5 rounded-full font-bold text-sm " + (p.hot ? "bg-green-600 text-white" : "border border-slate-300 text-slate-700")}>Choose {p.name}</Link>
              </div>
            ))}
          </div>
        </section>
