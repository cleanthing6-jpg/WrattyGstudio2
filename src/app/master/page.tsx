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

const PRESETS = ["afrobeats", "pop", "rap", "rnb", "amapiano", "dancehall", "gospel", "neutral"];

export default function MasterPage() {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [err, setErr] = useState("");
  const [url, setUrl] = useState("");
  
  // NEW: Metadata fields
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [name, setName] = useState("master.mp3");
  
  const [loud, setLoud] = useState("HIGH");
  const [preset, setPreset] = useState("afrobeats");
  const [info, setInfo] = useState("");

  const run = async (f: File) => {
    setBusy(true); setErr(""); setUrl(""); setInfo("");
    const base = f.name.replace(/\.[^.]+$/, "");
    
    // Create a professional filename
    const finalName = artist || title ? `${artist ? artist + " - " : ""}${title || base} - Master.mp3` : base + " - Master.mp3";
    setName(finalName);
    
    try {
      setStage("Uploading " + f.name + "...");
      const hosted = await uploadStem(f, "masters");

      setStage("Starting the master job...");
      // FIXED: Route through /api/master-render so ownership and cleanup logic runs
      const r = await fetch("/api/master-render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          url: hosted, 
          loudness: loud, 
          preset: preset,
          artist: artist,
          title: title || base
        }),
      });
      
      const d: any = await r.json().catch(() => ({}));
      if (!r.ok || !d.taskId) throw new Error(d?.error || "Could not start the master job (code " + r.status + ")");

      let finalUrl: string = d.url || "";
      let last: Job = {};
      
      for (let i = 0; i < 120 && !finalUrl; i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const g = await fetch("/api/master-render?taskId=" + encodeURIComponent(d.taskId));
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
        body: JSON.stringify({ name: finalName.replace(".mp3", ""), url: finalUrl, preset }),
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
          chain - adaptive EQ, PLR protection, and brickwall limiter.
        </p>

        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-sm text-slate-500 mb-2">Artist Name</label>
              <input type="text" placeholder="e.g. Burna Boy" value={artist} onChange={(e) => setArtist(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm" />
            </div>
            <div>
              <label className="block text-sm text-slate-500 mb-2">Song Name</label>
              <input type="text" placeholder="e.g. City Boys" value={title} onChange={(e) => setTitle(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm" />
            </div>
          </div>

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
              <label className="block text-sm text-slate-500 mb-2">Genre (Master Target)</label>
              <select value={preset} onChange={(e) => setPreset(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm">
                {PRESETS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          <div className="mt-6 border-t border-slate-100 pt-4">
            <label className="block text-sm text-slate-500 mb-2">Audio File</label>
            <input type="file" accept="audio/*" disabled={busy}
              onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) run(f); }}
              className="block w-full text-sm" />
          </div>

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
