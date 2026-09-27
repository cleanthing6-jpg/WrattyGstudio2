"use client";

import { useRef, useState } from "react";

type Status = "idle" | "starting" | "queued" | "running" | "done" | "failed";

const PRESETS = [
  "Afrobeats instrumental, log drum bass, shaker groove, 104 BPM, no vocals",
  "Afrobeats, amapiano log drums, airy pads, 112 BPM, instrumental",
  "Hip-Hop / Rap, boom bap drums, dusty piano loop, 90 BPM, instrumental",
  "Reggae / Dancehall, one-drop riddim, deep bass, 96 BPM, instrumental",
  "R&B, smooth chords, finger snaps, 84 BPM, instrumental",
];

export default function BeatPage() {
  const [prompt, setPrompt] = useState(PRESETS[0]);
  const [duration, setDuration] = useState(45);
  const [status, setStatus] = useState<Status>("idle");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const cancelled = useRef(false);

  const busy = status === "starting" || status === "queued" || status === "running";

  async function generate() {
    cancelled.current = false;
    setStatus("starting");
    setError("");
    setUrl("");
    setElapsed(0);

    try {
      const res = await fetch("/api/generate-beat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt, duration }),
      });
      const data = await res.json();
      if (!res.ok || !data?.job) {
        throw new Error(data?.error || "Could not start generation");
      }

      const job = data.job;
      const started = Date.now();
      setStatus("queued");

      for (let i = 0; i < 100; i++) {
        if (cancelled.current) return;
        await new Promise((r) => setTimeout(r, 3000));
        setElapsed(Math.round((Date.now() - started) / 1000));

        const s = await fetch(`/api/beat-status?job=${job}`).then((r) => r.json());
        if (s.status === "running") setStatus("running");
        if (s.status === "failed") throw new Error(s.error || "Generation failed");
        if (s.status === "done" && s.url) {
          setUrl(s.url);
          setStatus("done");
          return;
        }
      }
      throw new Error("Timed out after 5 minutes — try again");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setStatus("failed");
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Beat generator</h1>
        <p className="mt-1 text-sm opacity-70">
          Describe the beat you want. The first run can take a minute or two
          while the engine warms up; after that it is much faster.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPrompt(p)}
            className="rounded-full border px-3 py-1 text-xs"
          >
            {p.split(",")[0]}
          </button>
        ))}
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        className="w-full rounded-lg border p-3 text-sm"
        placeholder="e.g. Afrobeats instrumental, log drum bass, shaker groove, 104 BPM, no vocals"
      />

      <label className="flex items-center gap-3 text-sm">
        <span>Length</span>
        <input
          type="range"
          min={15}
          max={120}
          step={5}
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
        />
        <span className="tabular-nums">{duration}s</span>
      </label>

      <button
        type="button"
        onClick={generate}
        disabled={busy || !prompt.trim()}
        className="rounded-lg bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
      >
        {busy ? `Generating… ${elapsed}s` : "Generate beat"}
      </button>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {url && (
        <div className="space-y-3">
          <audio controls src={url} className="w-full" />
          <div className="flex gap-4 text-sm">
            <a href={url} download className="underline">
              Download
            </a>
            <button type="button" onClick={generate} className="underline">
              Generate another
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
