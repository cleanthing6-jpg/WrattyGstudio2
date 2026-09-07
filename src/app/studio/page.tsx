"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, Suspense, useRef, useCallback } from "react";
import MixUploader from "@/components/MixUploader";

type StudioTab = "beat" | "cover" | "mix";
type MixMode = "split" | "mix";
type StemRole = "lead" | "backup" | "adlib" | "beat";
type UploadedFile = { url: string; name: string; role: StemRole };
type SplitResult = { name: string; stems: { type: string; url: string }[] };
type ReadyStem = { url: string; name: string; role: StemRole };

function getStudioTab(value: string | null): StudioTab {
  return value === "beat" || value === "cover" || value === "mix" ? value : "beat";
}

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = getStudioTab(searchParams.get("type"));

  const [activeTab, setActiveTab] = useState<StudioTab>(initialType);
  const [mixMode, setMixMode] = useState<MixMode>("mix");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [splitResults, setSplitResults] = useState<SplitResult[]>([]);
  const [readyStems, setReadyStems] = useState<ReadyStem[]>([]);
  const [processing, setProcessing] = useState(false);
  const [stage, setStage] = useState("");
  const [mixedBlob, setMixedBlob] = useState<Blob | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const addFile = (url: string, name: string) => {
    setFiles((prev) => {
      if (prev.some((f) => f.url === url)) return prev;
      return [...prev, { url, name, role: "lead" }];
    });
  };

  const removeFile = (url: string) => {
    setFiles((prev) => prev.filter((f) => f.url !== url));
    setSplitResults((prev) => prev.filter((r) => r.name !== url));
    setReadyStems((prev) => prev.filter((s) => s.url !== url));
    setMixedBlob(null);
  };

  const setRole = (url: string, role: StemRole) => {
    setFiles((prev) => prev.map((f) => (f.url === url ? { ...f, role } : f)));
  };

  const promoteSplitStems = () => {
    const stems: ReadyStem[] = [];
    for (const r of splitResults) {
      for (const s of r.stems) {
        let role: StemRole = "beat";
        const t = (s.type || "").toLowerCase();
        if (t.includes("lead")) role = "lead";
        else if (t.includes("back")) role = "backup";
        else if (t.includes("ad")) role = "adlib";
        else if (t.includes("drum") || t.includes("bass") || t.includes("other") || t.includes("music") || t.includes("accompaniment") || t.includes("instrument")) role = "beat";
        stems.push({ url: s.url, name: s.type, role });
      }
    }
    setReadyStems(stems);
  };

  // ---- Split mode ----
  const runSplit = async () => {
    if (mixMode !== "split") return;
    if (!files.length) { alert("Upload at least one audio file first"); return; }
    setProcessing(true);
    setStage("Splitting track 1 of " + files.length + "…");
    const results: SplitResult[] = [];

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
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
          const files2 = sdata.data && sdata.data.files ? sdata.data.files : sdata.files;
          if (st === "done" && Array.isArray(files2)) {
            const stems = files2.filter((f: any) => f && f.url).map((f: any) => ({ type: f.type, url: f.url }));
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
      setStage("Splitting " + (i + 1) + " of " + files.length + "…");
    }

    setSplitResults(results);
    setStage("Split done — switch to Mix stems and press Auto mix & master");
    setProcessing(false);
  };

  // ---- Mix/master preset ----
  const applyPreset = useCallback(async (stems: ReadyStem[]) => {
    if (!stems.length) return null;
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    audioCtxRef.current = ctx;

    const normRole = (r: any, n: any) => {
      const t = String(r || n || "").toLowerCase();
      if (t.includes("beat") || t.includes("instrumental") || t.includes("drums") || t.includes("other")) return "beat";
      if (t.includes("back") || t.includes("harmony") || t.includes("chorus")) return "backing";
      if (t.includes("lead") || t.includes("main") || t.includes("vocal")) return "lead";
      if (t.includes("ad") || t.includes("adlib")) return "adlib";
      return "backing";
    };

    const load = (url: string) => fetch(url).then((r) => r.arrayBuffer()).then((ab) => ctx.decodeAudioData(ab));
    const buffers = await Promise.all(stems.map((s) => load(s.url)));
    const mixLen = Math.max(...buffers.map((b) => b.duration));
    const sampleRate = ctx.sampleRate;
    const length = Math.max(1, Math.ceil(mixLen * sampleRate));
    const offline = new OfflineAudioContext(2, length, sampleRate);

    const mixInput = offline.createGain();
    mixInput.gain.value = 1;
    mixInput.connect(offline.destination);

    const vocalBus = offline.createGain();
    vocalBus.gain.value = 1;
    vocalBus.connect(mixInput);

    for (let i = 0; i < stems.length; i++) {
      const role = normRole(stems[i].role, (stems[i] as any).name);
      const src = offline.createBufferSource();
      src.buffer = buffers[i];

      if (role === "beat") {
        const g = offline.createGain();
        g.gain.value = 0.85;
        const hp = offline.createBiquadFilter();
        hp.type = "highpass";
        hp.frequency.value = 28;
        src.connect(g);
        g.connect(hp);
        hp.connect(mixInput);
        src.start(0);
        continue;
      }

      const g = offline.createGain();
      g.gain.value = role === "lead" ? 1.0 : role === "adlib" ? 0.45 : 0.6;
      const hp = offline.createBiquadFilter();
      hp.type = "highpass";
      hp.frequency.value = 70;
      const lp = offline.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = 16000;
      const pan = offline.createStereoPanner();
      pan.pan.value = role === "lead" ? 0 : role === "adlib" ? (i % 2 === 0 ? 0.35 : -0.35) : (i % 2 === 0 ? -0.25 : 0.25);

      src.connect(g);
      g.connect(hp);
      hp.connect(lp);
      lp.connect(pan);
      pan.connect(vocalBus);
      src.start(0);
    }

    const rendered = await offline.startRendering();
    let peak = 0;
    for (let c = 0; c < rendered.numberOfChannels; c++) {
      const ch = rendered.getChannelData(c);
      for (let j = 0; j < ch.length; j++) {
        const a = Math.abs(ch[j]);
        if (a > peak) peak = a;
      }
    }
    const gainLinear = peak > 0.000001 ? Math.min(0.95 / peak, 64) : 1;
    for (let c = 0; c < rendered.numberOfChannels; c++) {
      const ch = rendered.getChannelData(c);
      for (let j = 0; j < ch.length; j++) {
        const v = ch[j] * gainLinear;
        ch[j] = v > 1 ? 1 : v < -1 ? -1 : v;
      }
    }
    return rendered;
  }, []);

  const bakeMix = async () => {
    if (mixMode !== "mix") return;
    const stems = readyStems.length ? readyStems : files.map((f) => ({ url: f.url, name: f.name, role: f.role }));
    if (!stems.length) { alert("Upload at least one vocal or beat first"); return; }
    setProcessing(true);
    setStage("Loading & analysing stems…");
    try {
      const result = await applyPreset(stems);
      if (!result) { setProcessing(false); return; }
      setMixedBlob(new Blob([encodeWav(result)], { type: "audio/wav" }));
      setStage("Done — preview and download");
    } catch (e: any) {
      alert("Mix failed: " + ((e && e.message) ? e.message : "unknown"));
    }
    setProcessing(false);
  };

  const downloadMix = () => {
    if (!mixedBlob) return;
    const url = URL.createObjectURL(mixedBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "WrattyG_ProfessionalMix.wav";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const encodeWav = (audioBuffer: AudioBuffer): ArrayBuffer => {
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
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
        offset += 2;
      }
    }
    return buffer;
  };

  const makeReverb = (ctx: OfflineAudioContext, decay: number, wet: number) => {
    const len = Math.ceil(ctx.sampleRate * decay);
    const impulse = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = impulse.getChannelData(c);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.2);
    }
    const conv = ctx.createConvolver();
    conv.buffer = impulse;
    const wetGain = ctx.createGain();
    wetGain.gain.value = wet;
    const dryGain = ctx.createGain();
    dryGain.gain.value = 1 - wet;
    const merger = ctx.createChannelMerger(2);
    conv.connect(wetGain);
    wetGain.connect(merger);
    dryGain.connect(merger);
    return merger;
  };

  const makeDelay = (ctx: OfflineAudioContext, delay: number, feedback: number, wet: number) => {
    const delayLine = ctx.createDelay(delay + 0.1);
    delayLine.delayTime.value = delay;
    const feedbackGain = ctx.createGain();
    feedbackGain.gain.value = feedback;
    const wetGain = ctx.createGain();
    wetGain.gain.value = wet;
    const dryGain = ctx.createGain();
    dryGain.gain.value = 1 - wet;
    delayLine.connect(feedbackGain);
    feedbackGain.connect(delayLine);
    delayLine.connect(wetGain);
    return dryGain;
  };

  const makeLimiter = (ctx: OfflineAudioContext, ceiling: number) => {
    const gain = ctx.createGain();
    gain.gain.value = 1;
    const shaper = ctx.createWaveShaper();
    const c = (ceiling / 100) + 1;
    const k = 10;
    shaper.curve = new Float32Array(256).map((_, i) => {
      const x = (i / 128) * 2 - 1;
      const y = Math.max(-1, Math.min(1, Math.sign(x) * (1 - Math.exp(-Math.abs(x) * k)) / (1 - Math.exp(-k))));
      return y / (Math.abs(y) + 0.0001) * Math.min(1, Math.abs(y)) * c;
    });
    gain.connect(shaper);
    shaper.connect(ctx.destination);
    return gain;
  };

  const approximateIntegratedLoudness = (buf: AudioBuffer): number => {
    let sum = 0;
    let count = 0;
    for (let c = 0; c < buf.numberOfChannels; c++) {
      const d = buf.getChannelData(c);
      for (let i = 0; i < d.length; i++) {
        sum += d[i] * d[i];
        count++;
      }
    }
    const meanSquare = sum / count;
    const linear = Math.sqrt(meanSquare);
    const db = 20 * Math.log10(linear + 1e-9);
    return db + 0.5;
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
            <p className="text-gray-500 text-sm mb-6">Upload your stems or a full song. We split if needed, then apply the professional preset.</p>

            <div className="space-y-4">
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
                  🎚️ Mix & master preset
                </button>
              </div>

              <div>
                <label className="block text-sm text-gray-500 mb-2">
                  {mixMode === "split"
                    ? "Upload the full song — lead, backups, and beat together. We split it into stems."
                    : "Upload your stems — lead vocal, backups, ad-libs, and the beat. Label each one."}
                </label>
                <MixUploader onReady={addFile} />
                {files.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {files.map((f) => (
                      <div key={f.url} className="flex items-center justify-between bg-green-50 border border-green-500/40 rounded-xl p-3">
                        <div className="flex-1 min-w-0">
                          <div className="text-green-700 font-semibold text-sm truncate">✅ {f.name}</div>
                          <select
                            value={f.role}
                            onChange={(e) => setRole(f.url, e.target.value as StemRole)}
                            className="mt-1 text-xs border border-slate-200 rounded-lg px-2 py-1 w-full bg-white"
                          >
                            <option value="lead">Lead vocal</option>
                            <option value="backup">Backing vocal</option>
                            <option value="adlib">Ad-lib</option>
                            <option value="beat">Beat / instrumental</option>
                          </select>
                          <audio controls src={f.url} className="w-full mt-1" preload="none" />
                        </div>
                        <button onClick={() => removeFile(f.url)} className="ml-2 text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {splitResults.length > 0 && (
                <div className="bg-green-50 border border-green-500/40 rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-green-700">✅ Split complete — {splitResults.reduce((a, r) => a + r.stems.length, 0)} stems</div>
                      <div className="text-xs text-gray-500">Switch to “Mix & master preset” and the app will assign each stem a role automatically.</div>
                    </div>
                    <button onClick={() => { promoteSplitStems(); setMixMode("mix"); }} className="bg-green-500 text-black font-bold px-4 py-2 rounded-xl hover:bg-green-400 transition text-sm">
                      Use stems in mixer
                    </button>
                  </div>
                </div>
              )}

              <button
                onClick={mixMode === "split" ? runSplit : bakeMix}
                disabled={processing || (mixMode === "split" ? !files.length : false) || (mixMode === "mix" ? !readyStems.length && !files.length : false)}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {processing
                  ? mixMode === "split" ? "Splitting " + files.length + " tracks… ⏳" : "Applying professional preset… ⏳"
                  : mixMode === "split"
                    ? "Split All Tracks (" + files.length + ") ✂️"
                    : "Auto mix & master preset 🎚️"}
              </button>
            </div>
          </div>

          {stage && !processing && stage !== "Done — preview and download" && (
            <p className="text-gray-500 text-sm text-center">{stage}</p>
          )}

          {splitResults.map((r) => (
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

          {mixedBlob && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30 text-center">
              <h3 className="font-bold mb-1 text-green-600">✅ Professional mix & master ready</h3>
              <p className="text-xs text-gray-500 mb-4">Lead in front, backups controlled, all vocals glued, mastered to streaming level</p>
              <audio controls src={URL.createObjectURL(mixedBlob)} className="w-full mb-4" preload="none" />
              <button onClick={downloadMix} className="bg-green-500 hover:bg-green-400 text-black font-bold py-3 px-8 rounded-xl transition">
                Download Mixed Master ⬇️
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
