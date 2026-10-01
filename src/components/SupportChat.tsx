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
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 rounded-full bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-lg"
      >
        💬 Help
      </button>
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
