"use client";

import { useState } from "react";

const WA = "https://wa.me/2347074216877";

type Turn = { role: "you" | "bot"; text: string };

export default function SupportChat() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([
    { role: "bot", text: "Hi! Ask me about renders, plans, uploads or refunds." },
  ]);

  async function send() {
    const q = msg.trim();
    if (!q || busy) return;
    setMsg("");
    setTurns((t) => [...t, { role: "you", text: q }]);
    setBusy(true);
    try {
      const r = await fetch("/api/support", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q }),
      });
      const d = await r.json().catch(() => ({}));
      setTurns((t) => [
        ...t,
        { role: "bot", text: d?.answer || "Something went wrong - try WhatsApp." },
      ]);
    } catch {
      setTurns((t) => [...t, { role: "bot", text: "Network error - try WhatsApp." }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2">
        <span className="animate-pulse rounded-full bg-slate-900/90 px-3 py-1.5 text-xs font-bold text-white shadow-lg">
          Need help? Tap the DJ
        </span>
        <button
          onClick={() => setOpen(true)}
          aria-label="Open support chat"
          title="Chat with support"
          className="group relative grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-green-500 via-emerald-600 to-slate-900 text-white shadow-2xl ring-4 ring-white/70 transition-transform duration-200 hover:scale-110 active:scale-95"
        >
          <span className="absolute inset-0 animate-ping rounded-full bg-green-400/40" />
          <svg
            viewBox="0 0 64 64"
            className="relative h-12 w-12"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M13 34v-3a19 19 0 0 1 38 0v3" />
            <rect x="7" y="32" width="9" height="15" rx="4.5" fill="currentColor" stroke="none" />
            <rect x="48" y="32" width="9" height="15" rx="4.5" fill="currentColor" stroke="none" />
            <circle cx="32" cy="34" r="10.5" />
            <path d="M28 38c1.2 1.8 6.8 1.8 8 0" />
          </svg>
          <span className="absolute -bottom-1 -right-1 grid h-6 w-6 place-items-center rounded-full bg-white text-[11px] font-black text-green-700 shadow">
            ?
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex h-96 w-80 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between bg-slate-900 px-3 py-2 text-sm font-semibold text-white">
        <span>Support</span>
        <button onClick={() => setOpen(false)} className="text-white/80">✕</button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3 text-xs">
        {turns.map((t, i) => (
          <div
            key={i}
            className={
              t.role === "you"
                ? "ml-8 rounded-lg bg-blue-600 px-3 py-2 text-white whitespace-pre-wrap"
                : "mr-8 rounded-lg bg-slate-100 px-3 py-2 text-slate-800 whitespace-pre-wrap"
            }
          >
            {t.text}
          </div>
        ))}
        {busy && <div className="mr-8 text-slate-400">thinking…</div>}
      </div>

      <div className="border-t border-slate-200 p-2">
        <div className="flex gap-2">
          <input
            value={msg}
            onChange={(e) => setMsg(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            placeholder="Type your question…"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-2 text-xs"
          />
          <button
            onClick={send}
            disabled={busy}
            className="rounded-lg bg-green-600 px-3 py-2 text-xs font-semibold text-white disabled:bg-slate-300"
          >
            Send
          </button>
        </div>
        <a
          href={WA}
          target="_blank"
          rel="noopener"
          className="mt-2 block text-center text-[11px] text-slate-500 underline"
        >
          Talk to a human on WhatsApp
        </a>
      </div>
    </div>
  );
}
