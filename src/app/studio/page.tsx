"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, Suspense, useRef, useCallback } from "react";
import MixUploader from "@/components/MixUploader";

type StudioTab = "beat" | "cover" | "mix";
type MixMode = "split" | "mix";
type UploadedFile = { url: string; name: string; kind: "lead" | "backup" | "beat" | "other" };

function getStudioTab(value: string | null): StudioTab {
  return value === "beat" || value === "cover" || value === "mix" ? value : "beat";
}

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = getStudioTab(searchParams.get("type"));

  const [activeTab, setActiveTab] = useState<StudioTab>(initialType);
  const [mixMode, setMixMode] = useState<MixMode>("split");
  const [mixFiles, setMixFiles] = useState<UploadedFile[]>([]);
  const [mixProcessing, setMixProcessing] = useState(false);
  const [splitResults, setSplitResults] = useState<{ name: string; stems: { type: string; url: string }[] }[]>([]);
  const [mixedBlob, setMixedBlob] = useState<Blob | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const addFile = (url: string, name: string) => {
    setMixFiles((prev) => {
      if (prev.some((f) => f.url === url)) return prev;
      return [...prev, { url, name, kind: "other" }];
    });
  };

  const removeFile = (url: string) => {
    setMixFiles((prev) => prev.filter((f) => f.url !== url));
    setSplitResults((prev) => prev.filter((r) => r.name !== url));
    setMixedBlob(null);
  };

  const setFileKind = (url: string, kind: UploadedFile["kind"]) => {
    setMixFiles((prev) => prev.map((f) => (f.url === url ? { ...f, kind } : f)));
  };

  // ---- Split mode (MVSEP) ----
  const runSplit = async () => {
    if (mixMode !== "split") return;
    if (!mixFiles.length) { alert("Upload at least one audio file first"); return; }
    setMixProcessing(true);
    const results: { name: string; stems: { type: string; url: string }[] }[] = [];

    for (let i = 0; i < mixFiles.length; i++) {
      const f = mixFiles[i];
      try {
        const res = await fetch("/api/mix-stems", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audioUrl: f.url }),
        });
        const data = await res.json();
        if (!data.taskId) { alert(f.name + " — " + (data.error || "Split failed")); continue; }
        let done = false;
        for (let p = 0; p < 60; p++) {
          await new Promise((r) => setTimeout(r, 10000));
          const sres = await fetch("/api/mix-status?hash=" + encodeURIComponent(data.taskId));
          const sdata = await sres.json();
          const st = sdata.status || (sdata.data && sdata.data.status);
          const files = sdata.data && sdata.data.files ? sdata.data.files : sdata.files;
          if (st === "done" && Array.isArray(files)) {
            const stems = files.filter((f: any) => f && f.url).map((f: any) => ({ type: f.type, url: f.url }));
            results.push({ name: f.name, stems });
            done = true;
            break;
          }
          if (st === "failed") { alert(f.name + " — split failed on server"); done = true; break; }
        }
        if (!done) alert(f.name + " — timed out, try again in a minute");
      } catch (e: any) {
        alert("Error splitting " + f.name + ": " + ((e && e.message) ? e.message : "network error"));
      }
    }
    setSplitResults(results);
    setMixProcessing(false);
  };

  // ---- Mix mode (browser-side Web Audio) ----
  const bakeMix = useCallback(async () => {
    if (mixMode !== "mix") return;
    if (!mixFiles.length) { alert("Upload at least one stem first"); return; }
    setMixProcessing(true);
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioCtxRef.current = ctx;
      const gains: { src: AudioBufferSourceNode; gain: GainNode }[] = [];
      const buffers: AudioBuffer[] = [];

      for (const f of mixFiles) {
        const resp = await fetch(f.url);
        const ab = await resp.arrayBuffer();
        const buf = await ctx.decodeAudioData(ab);
        buffers.push(buf);
      }

      const mixLen = Math.max(...buffers.map((b) => b.duration));
      const masterGain = ctx.createGain();
      masterGain.gain.value = 1;
      masterGain.connect(ctx.destination);

      for (let i = 0; i < mixFiles.length; i++) {
        const f = mixFiles[i];
        const buf = buffers[i];
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const gain = ctx.createGain();
        gain.gain.value = f.kind === "beat" ? 0.9 : 0.85;
        src.connect(gain);
        gain.connect(masterGain);
        src.start(0);
        gains.push({ src, gain });
      }

      const sampleRate = ctx.sampleRate;
      const numChannels = Math.min(2, masterGain.context.destination.channelCount || 2);
      const length = Math.ceil(mixLen * sampleRate);
      const offline = new OfflineAudioContext(numChannels, length, sampleRate);
      const offMaster = offline.createGain();
      offMaster.gain.value = 1;
      offMaster.connect(offline.destination);

      for (let i = 0; i < mixFiles.length; i++) {
        const f = mixFiles[i];
        const buf = buffers[i];
        const src = offline.createBufferSource();
        src.buffer = buf;
        const gain = offline.createGain();
        gain.gain.value = f.kind === "beat" ? 0.9 : 0.85;
        src.connect(gain);
        gain.connect(offMaster);
        src.start(0);
      }

      const rendered = await offline.startRendering();
      const wav = encodeWav(rendered);
      setMixedBlob(new Blob([wav], { type: "audio/wav" }));
    } catch (e: any) {
      alert("Mix failed: " + ((e && e.message) ? e.message : "unknown"));
    }
    setMixProcessing(false);
  }, [mixFiles, mixMode]);

  const downloadMix = () => {
    if (!mixedBlob) return;
    const url = URL.createObjectURL(mixedBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "WrattyG_Mix.wav";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const encodeWav = (audioBuffer: AudioBuffer): ArrayBuffer => {
    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const format = 1; // PCM
    const bitDepth = 16;
    const bytesPerSample = bitDepth / 8;
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
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitDepth, true);
    writeString(36, "data");
    view.setUint32(40, dataSize, true);
    let offset = 44;
    const channels: Float32Array[] = [];
    for (let c = 0; c < numChannels; c++) channels.push(audioBuffer.getChannelData(c));
    for (let i = 0; i < audioBuffer.length; i++) {
      for (let c = 0; c < numChannels; c++) {
        const sample = Math.max(-1, Math.min(1, channels[c][i] || 0));
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
        offset += 2;
      }
    }
    return buffer;
  };

  if (!user) return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading…</div>;

  return (
    <div className="min-h-screen bg-white px-4 py-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Studio</h1>
      <p className="text-gray-500 mb-8">Create beats, design covers, or process your tracks</p>

      <div className="flex gap-2 mb-8 overflow-x-auto">
        {[
          { id: "beat" as const, label: "🎵 Beat Generator" },
          { id: "cover" as const, label: "🎨 Album Cover" },
          { id: "mix" as const, label: "🎛️ Mix & Master" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 rounded-xl font-semibold whitespace-nowrap transition ${
              activeTab === tab.id
                ? "bg-green-500 text-black"
                : "bg-white text-gray-500 hover:text-slate-900 border border-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "mix" && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200">
            <h2 className="text-xl font-bold mb-4">Mix & Master</h2>
            <p className="text-gray-500 text-sm mb-6">Upload your stems or a full song. Choose what you need.</p>

            <div className="space-y-4">
              {/* Mode toggle */}
              <div className="flex gap-2">
                <button
                  onClick={() => setMixMode("split")}
                  className={`flex-1 py-3 rounded-xl font-semibold transition border ${
                    mixMode === "split"
                      ? "bg-green-500/10 border-green-500 text-slate-900"
                      : "bg-white border-slate-200 text-gray-500 hover:text-slate-900"
                  }`}
                >
                  ✂️ Split full song
                </button>
                <button
                  onClick={() => setMixMode("mix")}
                  className={`flex-1 py-3 rounded-xl font-semibold transition border ${
                    mixMode === "mix"
                      ? "bg-green-500/10 border-green-500 text-slate-900"
                      : "bg-white border-slate-200 text-gray-500 hover:text-slate-900"
                  }`}
                >
                  🎚️ Mix stems
                </button>
              </div>

              {/* Upload */}
              <div>
                <label className="block text-sm text-gray-500 mb-2">
                  {mixMode === "split"
                    ? "Upload the full song (beat + vocals together) — one file or several"
                    : "Upload your stems — lead vocal, each backup, and the beat"}
                </label>
                <MixUploader onReady={addFile} />
                {mixFiles.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {mixFiles.map((f) => (
                      <div key={f.url} className="flex items-center justify-between bg-green-50 border border-green-500/40 rounded-xl p-3">
                        <div className="flex-1 min-w-0">
                          <div className="text-green-700 font-semibold text-sm truncate">✅ {f.name}</div>
                          {mixMode === "mix" && (
                            <select
                              value={f.kind}
                              onChange={(e) => setFileKind(f.url, e.target.value as UploadedFile["kind"])}
                              className="mt-1 text-xs border border-slate-200 rounded-lg px-2 py-1 w-full bg-white"
                            >
                              <option value="lead">Lead vocal</option>
                              <option value="backup">Backing vocal</option>
                              <option value="beat">Beat / instrumental</option>
                              <option value="other">Other</option>
                            </select>
                          )}
                          <audio controls src={f.url} className="w-full mt-1" preload="none" />
                        </div>
                        <button onClick={() => removeFile(f.url)} className="ml-2 text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Action button */}
              <button
                onClick={mixMode === "split" ? runSplit : bakeMix}
                disabled={mixProcessing || !mixFiles.length}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {mixProcessing
                  ? mixMode === "split" ? "Splitting " + mixFiles.length + " tracks… ⏳" : "Mixing " + mixFiles.length + " stems… ⏳"
                  : mixMode === "split"
                    ? "Split All Tracks (" + mixFiles.length + ") ✂️"
                    : "Bake Mix & Download 🎚️"}
              </button>
            </div>
          </div>

          {/* Split results */}
          {mixMode === "split" && splitResults.map((r) => (
            <div key={r.name} className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-1 text-green-600">✅ {r.name} — stems ready</h3>
              <p className="text-xs text-gray-500 mb-3">{r.stems.length} stem{r.stems.length > 1 ? "s" : ""} — 320 kbps</p>
              <div className="space-y-3">
                {r.stems.map((s) => (
                  <div key={s.type + s.url} className="border border-slate-200 rounded-xl p-3">
                    <div className="font-semibold mb-2">{s.type}</div>
                    <audio controls src={s.url} className="w-full mb-2" preload="none" />
                    <a href={s.url} target="_blank" rel="noreferrer" download className="text-sm font-semibold text-green-600">Download {s.type} ⬇️</a>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Mix result */}
          {mixMode === "mix" && mixedBlob && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30 text-center">
              <h3 className="font-bold mb-1 text-green-600">✅ Mix baked</h3>
              <p className="text-xs text-gray-500 mb-4">All stems combined — download your final track</p>
              <audio controls src={URL.createObjectURL(mixedBlob)} className="w-full mb-4" preload="none" />
              <button onClick={downloadMix} className="bg-green-500 hover:bg-green-400 text-black font-bold py-3 px-8 rounded-xl transition">
                Download Mixed Track ⬇️
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Studio() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-500">Loading…</div>}>
      <StudioInner />
    </Suspense>
  );
}
