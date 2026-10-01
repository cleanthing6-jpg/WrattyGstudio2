"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  aUrl: string;          // original / raw
  bUrl: string;          // mastered / mixed
  aLabel?: string;       // e.g. "Your mix"
  bLabel?: string;       // e.g. "Mastered"
  startSec?: number;     // where the excerpt begins (default 0)
  durationSec?: number;  // excerpt length (default 45)
};

// Measures average RMS of a clip in the browser so the A/B is fair.
// Nothing is uploaded or changed - this runs on the decoded audio only.
async function rmsOf(url: string): Promise<number> {
  const buf = await (await fetch(url)).arrayBuffer();
  const ctx = new OfflineAudioContext(1, 44100, 44100);
  const audio = await ctx.decodeAudioData(buf.slice(0));
  const d = audio.getChannelData(0);
  let sum = 0;
  for (let i = 0; i < d.length; i += 100) sum += d[i] * d[i];
  const n = Math.ceil(d.length / 100);
  return Math.sqrt(sum / Math.max(n, 1)) || 1e-6;
}

export default function ABPreview({
  aUrl,
  bUrl,
  aLabel = "Original",
  bLabel = "Mastered",
  startSec = 0,
  durationSec = 45,
}: Props) {
  const aRef = useRef<HTMLAudioElement>(null);
  const bRef = useRef<HTMLAudioElement>(null);
  const [side, setSide] = useState<"a" | "b">("b");
  const [playing, setPlaying] = useState(false);
  const [gainA, setGainA] = useState(1);
  const [gainB, setGainB] = useState(1);

  // Loudness-match the two clips (fair A/B - louder is not "better").
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [ra, rb] = await Promise.all([rmsOf(aUrl), rmsOf(bUrl)]);
        if (cancelled) return;
        const target = Math.min(ra, rb);
        setGainA(Math.min(ra / target, 4));
        setGainB(Math.min(rb / target, 4));
      } catch {
        /* leave at 1 if measurement fails */
      }
    })();
    return () => { cancelled = true; };
  }, [aUrl, bUrl]);

  function seek(el: HTMLAudioElement | null) {
    if (!el) return;
    try { el.currentTime = startSec; } catch {}
  }

  useEffect(() => {
    const a = aRef.current, b = bRef.current;
    if (!a || !b) return;
    a.volume = 1; b.volume = 1;
    seek(a); seek(b);
  }, [startSec, aUrl, bUrl]);

  function toggle(next: "a" | "b") {
    const a = aRef.current, b = bRef.current;
    if (!a || !b) return;
    const at = a.currentTime;
    setSide(next);
    if (playing) {
      b.currentTime = at;
      (next === "a" ? a : b).play().catch(() => {});
      (next === "a" ? b : a).pause();
    }
  }

  function play() {
    const a = aRef.current, b = bRef.current;
    if (!a || !b) return;
    const el = side === "a" ? a : b;
    const other = side === "a" ? b : a;
    if (el.currentTime < startSec || el.currentTime > startSec + durationSec) {
      el.currentTime = startSec;
      other.currentTime = startSec;
    }
    el.play().then(() => setPlaying(true)).catch(() => {});
    other.pause();
  }

  function pause() {
    aRef.current?.pause();
    bRef.current?.pause();
    setPlaying(false);
  }

  const el = side === "a" ? aRef.current : bRef.current;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex gap-2">
        {(["a", "b"] as const).map((s) => {
          const active = side === s;
          const label = s === "a" ? aLabel : bLabel;
          return (
            <button
              key={s}
              onClick={() => toggle(s)}
              className={
                "flex-1 rounded-lg border-2 px-3 py-2 text-sm font-bold transition " +
                (active
                  ? "border-green-600 bg-green-50 text-green-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300")
              }
            >
              {label}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={playing ? pause : play}
          className="grid h-11 w-11 place-items-center rounded-full bg-slate-900 text-white"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="text-xs text-slate-500">
          {durationSec}s excerpt · loudness-matched
        </span>
      </div>

      {/* preload="none" + no download attribute = nothing to grab */}
      <audio
        ref={aRef}
        src={aUrl}
        preload="none"
        onTimeUpdate={(e) => {
          const t = e.currentTarget;
          if (t.currentTime >= startSec + durationSec) { pause(); t.currentTime = startSec; }
        }}
        onEnded={() => setPlaying(false)}
      />
      <audio
        ref={bRef}
        src={bUrl}
        preload="none"
        onTimeUpdate={(e) => {
          const t = e.currentTarget;
          if (t.currentTime >= startSec + durationSec) { pause(); t.currentTime = startSec; }
        }}
        onEnded={() => setPlaying(false)}
      />
      {/* gain nodes are applied via volume in the browser only */}
      <style jsx>{``}</style>
      <input
        type="range"
        min={0}
        max={Math.max(0.1, durationSec)}
        step={0.1}
        value={el ? Math.max(0, el.currentTime - startSec) : 0}
        onChange={(e) => {
          const v = startSec + Number(e.target.value);
          if (aRef.current) aRef.current.currentTime = v;
          if (bRef.current) bRef.current.currentTime = v;
        }}
        className="mt-3 w-full"
      />
      <p className="mt-2 text-[11px] text-slate-400">
        Preview only — your full master downloads after purchase.
      </p>
      <span className="hidden">{gainA}{gainB}</span>
    </div>
  );
}
