"use client";
import { useState } from "react";
import { useUploadThing } from "@/utils/uploadthing";

type Stem = { url: string; name: string; role: string };
type Phase = "idle" | "busy" | "preview" | "done";

const STYLES = ["HIPHOP_GRIME", "REGGAE_DUB", "POP", "ELECTRONIC", "ACOUSTIC", "ROCK_INDIE", "OTHER"];

let sharedCtx: AudioContext | null = null;
function getCtx() {
  if (!sharedCtx) sharedCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
  return sharedCtx;
}

function encodeWav(audioBuffer: AudioBuffer): ArrayBuffer {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = audioBuffer.length * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeString = (offset: number, str: string) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);
  let offset = 44;
  const channels: Float32Array[] = [];
  for (let c = 0; c < numChannels; c++) channels.push(audioBuffer.getChannelData(c));
  for (let i = 0; i < audioBuffer.length; i++) {
    for (let c = 0; c < numChannels; c++) {
      const sample = Math.max(-1, Math.min(1, channels[c][i] || 0));
      const dithered = Math.max(-1, Math.min(1, sample + (Math.random() - 0.5) * (1 / 32768)));
      view.setInt16(offset, dithered < 0 ? dithered * 0x8000 : dithered * 0x7FFF, true);
      offset += 2;
    }
  }
  return buffer;
}

export default function AiMixer({ stems }: { stems: Stem[] }) {
  const { startUpload } = useUploadThing("audioUploader");
  const [phase, setPhase] = useState<Phase>("idle");
  const [msg, setMsg] = useState("");
  const [style, setStyle] = useState("HIPHOP_GRIME");
  const [taskId, setTaskId] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [finalUrl, setFinalUrl] = useState("");
  const [finalName, setFinalName] = useState("");

  const ready = Array.isArray(stems) && stems.length >= 2;

  // RoEx needs WAV/AIFF/FLAC — convert mp3/etc stems in-browser to WAV first
  const toWav = async (st: Stem): Promise<Stem> => {
    if (/\.(wav|flac|aiff?)(\?|$)/i.test(st.url)) return st;
    const ab = await (await fetch(st.url)).arrayBuffer();
    const buf = await getCtx().decodeAudioData(ab);
    const wav = encodeWav(buf);
    const file = new File([wav], st.name.replace(/\.[^.]+$/, "") + ".wav", { type: "audio/wav" });
    const up = await startUpload([file]);
    const f: any = up && up[0];
    const url = (f && (f.ufsUrl || f.url || (f.serverData && f.serverData.url))) || "";
    if (!url) throw new Error("WAV conversion upload failed for " + st.name);
    return { url, name: st.name, role: st.role };
  };

  const toWavAll = async () => {
    const out: Stem[] = [];
    for (const s of stems) out.push(await toWav(s));
    return out;
  };

  const runPreview = async () => {
    if (!ready) { alert("Upload at least 2 stems (lead vocal + beat)"); return; }
    setPhase("busy");
    setMsg("Converting stems to WAV…");
    try {
      const wavStems = await toWavAll();
      setMsg("Sending stems to the RoEx AI engine…");
      const res = await fetch("/api/roex-mix", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stems: wavStems, style }),
      });
      const data = await res.json();
      if (!data.taskId) throw new Error(data.error || "RoEx task failed");
      setTaskId(data.taskId);
      setMsg("RoEx is mixing your stems (30s preview)…");
      for (let p = 0; p < 60; p++) {
        await new Promise((r) => setTimeout(r, 3000));
        const sres = await fetch("/api/roex-mix?taskId=" + encodeURIComponent(data.taskId));
        const sdata = await sres.json();
        if (sdata.status === "preview" && sdata.url) {
          setPreviewUrl(sdata.url);
          setPhase("preview");
          setMsg("30s preview ready — listen, then unlock the full mix.");
          return;
        }
        if (sdata.error) throw new Error(sdata.error);
      }
      throw new Error("Preview timed out — try again");
    } catch (e: any) {
      alert("AI preview failed: " + ((e && e.message) ? e.message : "unknown"));
      setPhase("idle");
      setMsg("");
    }
  };

  const unlockFull = async () => {
    if (!taskId) { alert("Generate the preview first"); return; }
    setPhase("busy");
    setMsg("Unlocking full AI mix — this uses RoEx credits…");
    try {
      const wavStems = await toWavAll();
      const res = await fetch("/api/roex-full", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId, stems: wavStems }),
      });
      const data = await res.json();
      if (!data.url) throw new Error(data.error || "Full mix failed");
      const beat = stems.find((s) => String(s.role || s.name).toLowerCase().includes("beat"));
      const base = (beat && beat.name ? beat.name : stems[0] && stems[0].name ? stems[0].name : "Mix").replace(/\.[^.]+$/, "");
      const label = base + " - AI Master";
      setFinalName(label);
      setMsg("Downloading master from RoEx & saving to your dashboard…");
      const blob = await (await fetch(data.url)).blob();
      const up = await startUpload([new File([blob], label + ".wav", { type: "audio/wav" })]);
      const f: any = up && up[0];
      const hosted = (f && (f.ufsUrl || f.url || (f.serverData && f.serverData.url))) || "";
      if (hosted) {
        try {
          await fetch("/api/mixes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: label, url: hosted }),
          });
        } catch {}
      }
      setFinalUrl(hosted || data.url);
      setPhase("done");
      setMsg("Done — saved to Dashboard > My Mixes");
    } catch (e: any) {
      alert("Full mix failed: " + ((e && e.message) ? e.message : "unknown"));
      setPhase(previewUrl ? "preview" : "idle");
      setMsg("");
    }
  };

  return (
    <div className="bg-white rounded-2xl p-6 border border-blue-200 mt-6">
      <h3 className="text-lg font-bold mb-1">✨ AI Mix & Master (Pro Engine)</h3>
      <p className="text-xs text-gray-500 mb-3">Powered by the RoEx Tonn engine. Preview is free; the full mix uses 1 AI credit.</p>
      {!ready && <p className="text-sm text-gray-400">Upload at least 2 stems (e.g. lead vocal + beat) to enable the AI engine.</p>}
      {ready && (
        <div className="space-y-3">
          <label className="block text-xs text-gray-500">Musical style</label>
          <select value={style} onChange={(e) => setStyle(e.target.value)} className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm">
            {STYLES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
          </select>
          <button
            onClick={runPreview}
            disabled={phase === "busy"}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-100 disabled:text-gray-500 text-white font-bold py-3 rounded-xl transition text-sm"
          >
            {phase === "busy" ? "Processing… ⏳" : "🔊 Generate free 30s AI preview"}
          </button>
          {previewUrl && (
            <div className="space-y-3">
              <audio controls src={previewUrl} className="w-full" preload="none" />
              <button
                onClick={unlockFull}
                disabled={phase === "busy"}
                className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-100 disabled:text-gray-500 text-white font-bold py-3 rounded-xl transition text-sm"
              >
                {phase === "busy" ? "Unlocking… ⏳" : "💎 Unlock full AI mix (1 credit)"}
              </button>
            </div>
          )}
          {finalUrl && (
            <div className="bg-green-50 border border-green-500/40 rounded-xl p-3">
              <p className="text-sm font-semibold text-green-700 mb-2">✅ {finalName}</p>
              <audio controls src={finalUrl} className="w-full mb-2" preload="none" />
              <a href={finalUrl} download={finalName + ".wav"} className="text-xs font-bold text-blue-600 underline">⬇ Download WAV</a>
            </div>
          )}
          {msg && <p className="text-xs text-gray-500">{msg}</p>}
        </div>
      )}
    </div>
  );
}
