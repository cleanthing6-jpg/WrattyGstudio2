// src/components/AutoTuneToggle.tsx
"use client";
import { useEffect, useRef, useState } from "react";
import type { useAutoTune } from "@/hooks/useAutoTune";
import { PianoRollConsole } from "./PianoRollConsole";

function useCountUp(target: number, running: boolean) {
  const [v, setV] = useState(0);
  const lastTargetAt = useRef(Date.now());
  const lastCreepAt = useRef(Date.now());

  useEffect(() => {
    if (running) {
      setV(0);
      lastTargetAt.current = Date.now();
      lastCreepAt.current = Date.now();
    }
  }, [running]);

  useEffect(() => {
    lastTargetAt.current = Date.now();
  }, [target]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setV((cur) => {
        if (cur < target) return Math.min(cur + 2, target);
        if (Date.now() - lastTargetAt.current > 2500) {
          const cap = Math.min(target + 15, 95);
          if (cur < cap && Date.now() - lastCreepAt.current > 500) {
            lastCreepAt.current = Date.now();
            return cur + 1;
          }
        }
        return cur;
      });
    }, 40);
    return () => clearInterval(id);
  }, [running, target]);

  return running ? Math.max(1, v) : v;
}

export function AutoTuneToggle({ tune }: { tune: ReturnType<typeof useAutoTune> }) {
  const running = tune.state === "running";
  const shown = useCountUp(tune.pct, running);

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3 mb-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-semibold text-gray-800">Auto-tune lead vocal</div>
          <div className="text-xs text-gray-500">Tuned to the beat's key before it hits the mix bus</div>
        </div>
        <button
          role="switch"
          aria-checked={tune.enabled}
          disabled={running}
          onClick={() => tune.setEnabled(!tune.enabled)}
          className={`relative h-7 w-12 rounded-full transition-colors ${tune.enabled ? "bg-emerald-500" : "bg-gray-300"} disabled:opacity-50`}
        >
          <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all ${tune.enabled ? "left-5" : "left-0.5"}`} />
        </button>
      </div>

      {tune.enabled && (
        <div className="flex gap-2 text-sm">
          {(["natural", "hard"] as const).map((p) => (
            <button key={p} disabled={running} onClick={() => tune.setPreset(p)}
              className={`rounded-lg px-3 py-1 font-medium transition-colors ${tune.preset === p ? "bg-gray-200 text-gray-900" : "bg-white border border-gray-300 text-gray-600 hover:bg-gray-100"}`}>
              {p === "natural" ? "Natural (Smooth)" : "Hard Snap"}
            </button>
          ))}
        </div>
      )}

      {running && (
        <div className="space-y-1">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-gray-700">{tune.stage}…</span>
            <span className="tabular-nums font-semibold text-gray-900">{shown}% · {tune.seconds}s</span>
          </div>
          <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${shown}%` }} />
          </div>
        </div>
      )}
      
      {tune.state === "done" && (
          <>
            <div className="text-xs font-semibold text-emerald-600">Tuned{tune.key ? ` in ${tune.key}` : ""} ✓</div>
            <PianoRollConsole pianoRoll={tune.pianoRoll} />
          </>
        )}
      {tune.state === "failed" && <div className="text-xs font-semibold text-amber-600">Tuning failed, using original. ({tune.stage})</div>}
    </div>
  );
}
