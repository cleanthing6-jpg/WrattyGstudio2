"use client";
import { useCallback, useEffect, useState } from "react";

export type Stem = { url: string; name: string; role: string };
export type TuneState = "idle" | "running" | "done" | "failed";
export type TunePreset = "natural" | "hard";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useAutoTune() {
  const [enabled, setEnabled] = useState(false);
  const [preset, setPreset] = useState<TunePreset>("natural");
  const [state, setState] = useState<TuneState>("idle");
  const [pct, setPct] = useState(0);
  const [stage, setStage] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [key, setKey] = useState<string | null>(null);
  const [pianoRoll, setPianoRoll] = useState<any[]>([]);

  useEffect(() => {
    if (state !== "running") return;
    const t0 = Date.now();
    setSeconds(0);
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - t0) / 1000)), 250);
    return () => clearInterval(id);
  }, [state]);

  const applyToStems = useCallback(
    async (stems: Stem[]): Promise<Stem[]> => {
      const lead = stems.find((s) => s.role === "lead");
      if (!enabled || !lead) return stems;
      const beat = stems.find((s) => s.role === "beat" || s.role === "instrumental");

      setState("running"); setPct(0); setStage("Starting"); setKey(null); setPianoRoll([]);
      try {
        const start = await fetch("/api/tune", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ url: lead.url, beatUrl: beat?.url, preset }),
        });
        if (!start.ok) throw new Error("start failed");
        const { jobId } = await start.json();

        const deadline = Date.now() + 10 * 60 * 1000;
        while (Date.now() < deadline) {
          await sleep(600);
          const r = await fetch(`/api/tune/${jobId}`, { cache: "no-store" });
          if (!r.ok) continue;
          const s = await r.json();
          if (typeof s.pct === "number") setPct(s.pct);
          if (s.stage) setStage(s.stage);
          if (s.status === "error") throw new Error(s.error || "tune error");
          if (s.status === "done" && s.url) {
            setPct(100); setState("done");
            setKey(s.detectedKey ?? s.key ?? null);
            setPianoRoll(s.pianoRoll ?? []);
            return stems.map((x) => (x === lead ? { ...x, url: s.url } : x));
          }
        }
        throw new Error("timeout");
      } catch (e: any) {
        console.error("Tune error:", e);
        setState("failed");
        setStage(e?.message || "Tune failed");
        return stems;
      }
    },
    [enabled, preset]
  );

  return { enabled, setEnabled, preset, setPreset, state, pct, stage, seconds, key, pianoRoll, applyToStems };
}
