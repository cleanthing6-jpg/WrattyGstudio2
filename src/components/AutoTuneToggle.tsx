// src/components/AutoTuneToggle.tsx   (Tailwind classes; swap for your own styling if needed)
"use client";
import { useEffect, useState } from "react";
import type { useAutoTune } from "@/hooks/useAutoTune";

function useCountUp(target: number) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (target === 0) { setV(0); return; }
    const id = setInterval(() => setV((cur) => (cur < target ? cur + 1 : cur)), 25);
    return () => clearInterval(id);
  }, [target]);
  return v;
}

export function AutoTuneToggle({ tune }: { tune: ReturnType<typeof useAutoTune> }) {
  const shown = useCountUp(tune.pct);
  const running = tune.state === "running";

  return (
    <div className="rounded-xl border border-white/10 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">Auto-tune lead vocal</div>
          <div className="text-xs opacity-60">Tuned to the beat's key before it hits the mix bus</div>
        </div>
        <button
          role="switch"
          aria-checked={tune.enabled}
          disabled={running}
          onClick={() => tune.setEnabled(!tune.enabled)}
          className={`relative h-7 w-12 rounded-full transition ${tune.enabled ? "bg-emerald-500" : "bg-white/20"} disabled:opacity-50`}
        >
          <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white transition-all ${tune.enabled ? "left-5" : "left-0.5"}`} />
        </button>
      </div>

      {tune.enabled && (
        <div className="flex gap-2 text-sm">
          {(["natural", "hard"] as const).map((p) => (
            <button key={p} disabled={running} onClick={() => tune.setPreset(p)}
              className={`rounded-lg px-3 py-1 ${tune.preset === p ? "bg-white/20" : "bg-white/5"}`}>
              {p === "natural" ? "Natural (R&B)" : "Hard snap (rap)"}
            </button>
          ))}
        </div>
      )}

      {running && (
        <div className="space-y-1">
          <div className="flex items-baseline justify-between text-sm">
            <span>{tune.stage}…</span>
            <span className="tabular-nums font-semibold">{shown}% · {tune.seconds}s</span>
          </div>
          <div className="h-2 rounded bg-white/10 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${shown}%` }} />
          </div>
        </div>
      )}
      {tune.state === "done" && <div className="text-xs text-emerald-400">Tuned{tune.key ? ` in ${tune.key}` : ""} ✓</div>}
      {tune.state === "failed" && <div className="text-xs text-amber-400">Tuning failed, using the original vocal.</div>}
    </div>
  );
}
