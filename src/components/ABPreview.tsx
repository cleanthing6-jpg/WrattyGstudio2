"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  aUrl: string;
  bUrl: string;
  aLabel?: string;
  bLabel?: string;
  startSec?: number;
  durationSec?: number;
};

export default function ABPreview({
  aUrl,
  bUrl,
  aLabel = "Original",
  bLabel = "Mastered",
  startSec = 0,
  durationSec = 30,
}: Props) {
  const aRef = useRef<HTMLAudioElement>(null);
  const bRef = useRef<HTMLAudioElement>(null);
  const [side, setSide] = useState<"a" | "b">("b");
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);

  function both(fn: (el: HTMLAudioElement) => void) {
    if (aRef.current) fn(aRef.current);
    if (bRef.current) fn(bRef.current);
  }

  function pause() {
    both((el) => el.pause());
    setPlaying(false);
  }

  function play() {
    const a = aRef.current, b = bRef.current;
    if (!a || !b) return;
    
    if (side === "a" && !aUrl) return;
    if (side === "b" && !bUrl) return;

    const el = side === "a" ? a : b;
    const other = side === "a" ? b : a;

    if (el.currentTime < startSec || el.currentTime >= startSec + durationSec) {
      a.currentTime = startSec;
      b.currentTime = startSec;
    }
    other.pause();
    
    el.play()
      .then(() => setPlaying(true))
      .catch((err) => {
        console.error("Playback failed:", err);
        setPlaying(false);
      });
  }

  function toggle(next: "a" | "b") {
    const a = aRef.current, b = bRef.current;
    if (!a || !b) return;
    if (next === "a" && !aUrl) return;
    if (next === "b" && !bUrl) return;

    const at = a.currentTime;
    setSide(next);
    if (playing) {
      a.pause(); b.pause();
      b.currentTime = at;
      const el = next === "a" ? a : b;
      el.currentTime = at;
      el.play().catch(() => setPlaying(false));
    }
  }

  const clipEnd = startSec + durationSec;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex gap-2">
        {(["a", "b"] as const).map((s) => {
          const active = side === s;
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
              {s === "a" ? aLabel : bLabel}
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
          {playing ? "II" : ">"}
        </button>
        <span className="text-xs text-slate-500">
          {durationSec}s excerpt
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={durationSec}
        step={0.1}
        value={Math.max(0, t - startSec)}
        onChange={(e) => {
          const v = startSec + Number(e.target.value);
          both((el) => { el.currentTime = v; });
          setT(v);
        }}
        className="mt-3 w-full"
      />

      <p className="mt-2 text-[11px] text-slate-400">
        Preview only — your full master downloads after purchase.
      </p>

      {aUrl && (
        <audio
          ref={aRef}
          src={aUrl}
          preload="none"
          onTimeUpdate={(e) => {
            if (side !== "a") return;
            const el = e.currentTarget;
            setT(el.currentTime);
            if (el.currentTime >= clipEnd) {
              el.pause();
              both((x) => { x.currentTime = startSec; });
              setT(startSec);
              setPlaying(false);
            }
          }}
          onEnded={() => setPlaying(false)}
          onError={() => setPlaying(false)}
        />
      )}
      {bUrl && (
        <audio
          ref={bRef}
          src={bUrl}
          preload="none"
          onTimeUpdate={(e) => {
            if (side !== "b") return;
            const el = e.currentTarget;
            setT(el.currentTime);
            if (el.currentTime >= clipEnd) {
              el.pause();
              both((x) => { x.currentTime = startSec; });
              setT(startSec);
              setPlaying(false);
            }
          }}
          onEnded={() => setPlaying(false)}
          onError={() => setPlaying(false)}
        />
      )}
    </div>
  );
}
