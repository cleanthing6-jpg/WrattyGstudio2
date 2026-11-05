"use client";

import { useEffect, useRef, useState } from "react";
import { ABPlayer, State } from "@/lib/abPlayer";

type Props = {
  aUrl: string;
  bUrl: string;
  aLabel?: string;
  bLabel?: string;
};

export default function ABPreview({ aUrl, bUrl, aLabel = "Before Mix", bLabel = "After Mix Preview" }: Props) {
  const rawRef = useRef<HTMLAudioElement>(null);
  const mixedRef = useRef<HTMLAudioElement>(null);
  const playerRef = useRef<ABPlayer | null>(null);
  const [state, setState] = useState<State | null>(null);

  useEffect(() => {
    if (!rawRef.current || !mixedRef.current) return;

    const player = new ABPlayer({
      raw: rawRef.current,
      mixed: mixedRef.current,
      onChange: setState,
    });

    playerRef.current = player;
    player.load(aUrl, bUrl);

    return () => {
      player.destroy();
      playerRef.current = null;
    };
  }, [aUrl, bUrl]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      {!state ? (
        <div className="text-xs text-slate-500 animate-pulse">Loading A/B player...</div>
      ) : (
        <>
          <div className="mb-3 flex gap-2">
            <button
              onClick={() => playerRef.current?.select("raw")}
              disabled={state.phase === "error"}
              className={`flex-1 rounded-lg border-2 px-3 py-2 text-sm font-bold transition ${
                state.active === "raw"
                  ? "border-green-600 bg-green-50 text-green-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 disabled:opacity-50"
              }`}
            >
              {aLabel}
            </button>
            <button
              onClick={() => playerRef.current?.select("mixed")}
              disabled={state.phase === "error"}
              className={`flex-1 rounded-lg border-2 px-3 py-2 text-sm font-bold transition ${
                state.active === "mixed"
                  ? "border-green-600 bg-green-50 text-green-800"
                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 disabled:opacity-50"
              }`}
            >
              {bLabel}
            </button>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => (state.phase === "playing" ? playerRef.current?.pause() : playerRef.current?.play())}
              disabled={state.phase === "error" || state.phase === "loading"}
              className="grid h-11 w-11 place-items-center rounded-full bg-slate-900 text-white disabled:opacity-50"
            >
              {state.phase === "playing" ? "II" : ">"}
            </button>
            <span className="text-xs text-slate-500">
              {state.message || (state.phase === "loading" ? "Loading both previews..." : `${Math.round(state.time)}s / 30s`)}
            </span>
          </div>

          <input
            type="range"
            min={0}
            max={state.duration || 30}
            step={0.1}
            value={state.time}
            onChange={(e) => playerRef.current?.seek(Number(e.target.value))}
            disabled={state.phase === "error" || state.phase === "loading"}
            className="mt-3 w-full disabled:opacity-50"
          />

          {state.phase === "error" && (
            <div className="mt-2 rounded-lg bg-red-50 p-2 text-xs font-semibold text-red-600">
              ⚠️ {state.message}
            </div>
          )}

          <p className="mt-2 text-[11px] text-slate-400">
            Preview only — your full master downloads after purchase.
          </p>
        </>
      )}
      
      {/* Hidden Audio Elements - ALWAYS MOUNTED */}
      <audio ref={rawRef} preload="auto" className="hidden" />
      <audio ref={mixedRef} preload="auto" className="hidden" />
    </div>
  );
}
