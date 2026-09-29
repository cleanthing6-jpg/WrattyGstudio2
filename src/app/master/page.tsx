"use client";
import { useState } from "react";
import { uploadStem } from "@/lib/freeUpload";

type Job = {
  status?: string;
  position?: number;
  url?: string;
  error?: string;
  result?: any;
};

const PRESETS = ["afrobeats", "pop", "rap", "rnb", "amapiano", "neutral"];

export default function MasterPage() {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [err, setErr] = useState("");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("master.mp3");
  const [loud, setLoud] = useState("HIGH");
  const [preset, setPreset] = useState("afrobeats");
  const [info, setInfo] = useState("");

  const run = async (f: File) => {
    setBusy(true); setErr(""); setUrl(""); setInfo("");
    const base = f.name.replace(/\.[^.]+$/, "");
    setName(base + " - Master.mp3");
    try {
      setStage("Uploading " + f.name + "...");
      const hosted = await uploadStem(f, "masters");

      setStage("Starting the master job...");
      const r = await fetch("/api/mix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stems: [{ url: hosted, role: "master" }], loudness: loud, preset }),
      });
      const d: any = await r.json().catch(() => ({}));
      if (!r.ok || !d.job) throw new Error(d?.error || "Could not start the master job (code " + r.status + ")");

      let finalUrl: string = d.url || "";
      let last: Job = {};
      for (let i = 0; i < 120 && !finalUrl; i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const g = await fetch("/api/mix?id=" + encodeURIComponent(d.job));
        const gd: Job = await g.json().catch(() => ({}));
        last = gd;
        if (gd.status === "failed") throw new Error(gd.error || "Mastering failed");
        if (gd.error && gd.status !== "queued" && gd.status !== "running") throw new Error(String(gd.error));
        if (gd.status === "done" && gd.url) { finalUrl = gd.url; break; }
        setStage(gd.status === "queued"
          ? "Queued - position " + (gd.position || 1) + ". It will start automatically."
          : "Mastering... " + ((i + 1) * 5) + "s");
      }
      if (!finalUrl) throw new Error("Still working - do not resubmit. Check Dashboard > My Mixes in a minute.");
      setUrl(finalUrl);

      const m: any = last.result && typeof last.result === "object" ? last.result : {};
      setInfo([
        typeof m.lufs === "number" ? m.lufs.toFixed(2) + " LUFS" : "",
        typeof m.peak_dbfs === "number" ? m.peak_dbfs.toFixed(2) + " dBFS peak" : "",
        typeof m.seconds === "number" ? m.seconds.toFixed(1) + "s" : "",
        m.mode ? "mode: " + m.mode : "",
      ].filter(Boolean).join("   "));

      setStage("Saving to your dashboard...");
      const s = await fetch("/api/mixes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: base + " - Master", url: finalUrl, preset }),
      });
      setStage(s.ok ? "Done - saved to Dashboard > My Mixes" : "Master ready - dashboard save failed, download it now");
    } catch (e: any) {
      setErr(e?.message || "unknown error");
      setStage("");
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-[#faf9f4] p-4 text-slate-900">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-black mb-1">Master only</h1>
        <p className="text-slate-500 text-sm mb-6">
          Upload an already-mixed song. It goes through the studio engine's master
          chain - polish EQ, width, brickwall limiter. Free accounts render a 30s preview.
        </p>

        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-sm text-slate-500 mb-2">Loudness</label>
              <select value={loud} onChange={(e) => setLoud(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm">
                <option value="MEDIUM">Standard</option>
                <option value="HIGH">Loud</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-500 mb-2">Style</label>
              <select value={preset} onChange={(e) => setPreset(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm">
                {PRESETS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          <input type="file" accept="audio/*" disabled={busy}
            onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) run(f); }}
            className="block w-full text-sm" />

          {stage && <p className="mt-4 text-sm text-slate-500">{stage}</p>}
          {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
          {info && <p className="mt-2 text-xs text-slate-400 break-all">{info}</p>}
        </div>

        {url && (
          <div className="mt-6 bg-white rounded-2xl border border-slate-200 p-6">
            <p className="font-bold text-green-700 mb-2">Master ready</p>
            <audio controls src={url} className="w-full" />
            <a href={url} download={name}
              className="mt-3 inline-block px-5 py-3 rounded-full bg-green-600 text-white font-bold text-sm">
              Download master
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
