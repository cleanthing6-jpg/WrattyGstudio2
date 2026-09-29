"use client";
import { masterStage } from "@/lib/masterStage";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, Suspense, useRef, useCallback, useEffect } from "react";
import MixUploader from "@/components/MixUploader";
import AiMixer from "@/components/AiMixer";
import { uploadStem } from "@/lib/freeUpload";

async function localStartUpload(files: any[]): Promise<any[]> {
  const out: any[] = [];
  const list = Array.isArray(files) ? files : [files];
  for (let i = 0; i < list.length; i++) {
    const f: any = list[i];
    const name = (f && f.name) || "stem.wav";
    const file = new File([f], name, { type: (f && f.type) || "audio/wav" });
    const url = await uploadStem(file);
    out.push({ ufsUrl: url, url, serverData: { ufsUrl: url, url } });
  }
  return out;
}

const startUpload = localStartUpload;


async function loudnessNormalize(buf: AudioBuffer): Promise<AudioBuffer> {
  const channels = buf.numberOfChannels;
  const length = buf.length;
  const channelData: Float32Array[] = [];
  let sumSq = 0;
  let peak = 0;
  for (let c = 0; c < channels; c++) {
    const data = buf.getChannelData(c);
    channelData.push(data);
    for (let i = 0; i < length; i++) {
      const v = data[i] || 0;
      sumSq += v * v;
      const a = Math.abs(v);
      if (a > peak) peak = a;
    }
  }
  const rms = Math.sqrt(sumSq / (channels * length));
  const targetRms = 0.18;
  const rmsGain = targetRms / Math.max(rms, 1e-6);
  let tp = peak;
  for (let c = 0; c < channels; c++) {
    const data = channelData[c];
    for (let i = 0; i < length - 1; i++) {
      const a = data[i] || 0;
      const b = data[i + 1] || 0;
      for (let j = 1; j < 4; j++) {
        const v = a + (b - a) * (j / 4);
        const av = Math.abs(v);
        if (av > tp) tp = av;
      }
    }
  }
  const peakSafeGain = tp > 0.000001 ? 0.85 / tp : 1;
  const gain = Math.min(rmsGain, peakSafeGain, 8);
  const out = new OfflineAudioContext(channels, length, buf.sampleRate);
  const src = out.createBufferSource();
  src.buffer = buf;
  const g = out.createGain();
  g.gain.value = gain;
  const limiter = out.createDynamicsCompressor();
  limiter.threshold.value = -6;
  limiter.ratio.value = 4;
  limiter.attack.value = 0.005;
  limiter.release.value = 0.25;
  src.connect(g);
  g.connect(limiter);
  limiter.connect(out.destination);
  src.start(0);
  return await out.startRendering();
}


async function loadSpaceIR(mode: string, ctx: OfflineAudioContext, cfg: { decay: number; damp: number; predelay: number; ret: number }): Promise<ConvolverNode> {
  const urls: Record<string, string> = {
    room: "/ir/room.wav",
    hall: "/ir/hall.wav",
    cathedral: "/ir/cathedral.wav",
    plate: "/ir/plate.wav",
    studio: ""
  };
  const url = urls[mode] || "";
  let real: AudioBuffer | null = null;
  if (url) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        real = await ctx.decodeAudioData(await res.arrayBuffer());
      }
    } catch {
      real = null;
    }
  }
  const conv = ctx.createConvolver();
  conv.normalize = true;
  if (real) {
    conv.buffer = real;
    return conv;
  }
  const len = Math.max(1, Math.floor(ctx.sampleRate * cfg.decay));
  const buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let c = 0; c < 2; c++) {
    const data = buf.getChannelData(c);
    for (let i = 0; i < len; i++) {
      const secs = i / ctx.sampleRate;
      const env = Math.exp(-3.0 * (1.8 / cfg.decay) * secs) * (c === 0 ? 0.9 : 1.0);
      data[i] = (Math.random() * 2 - 1) * env;
    }
  }
  conv.buffer = buf;
  return conv;
}

type StudioTab = "mix";
type SpaceMode = "studio" | "room" | "hall" | "cathedral" | "plate";
type StemRole = "lead" | "backup" | "adlib" | "beat";
type UploadedFile = { url: string; name: string; role: StemRole };
type ReadyStem = { url: string; name: string; role: StemRole };

function getStudioTab(_value: string | null): StudioTab {
  return "mix";
}

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = getStudioTab(searchParams.get("type"));

  const [activeTab, setActiveTab] = useState<StudioTab>(initialType);
  const [spaceMode, setSpaceMode] = useState<SpaceMode>("studio");
  const spaceRef = useRef<SpaceMode>("studio");
  spaceRef.current = spaceMode;
  const [files, setFiles] = useState<UploadedFile[]>([]);

  const [wgsStemsHydrated, setWgsStemsHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("wgs:stems");
      if (raw) {
        const saved = JSON.parse(raw);
        if (Array.isArray(saved)) setFiles(saved as UploadedFile[]);
      }
    } catch {}
    setWgsStemsHydrated(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !wgsStemsHydrated) return;
    try {
      window.localStorage.setItem("wgs:stems", JSON.stringify(files));
    } catch {}
  }, [files, wgsStemsHydrated]);

  const [readyStems, setReadyStems] = useState<ReadyStem[]>([]);
  const [processing, setProcessing] = useState(false);
  const [stage, setStage] = useState("");
  const audioCtxRef = useRef<AudioContext | null>(null);

  const addFile = (url: string, name: string) => {
    setFiles((prev) => {
      if (prev.some((f) => f.url === url)) return prev;
      return [...prev, { url, name, role: "lead" }];
    });
  };

  const removeFile = (url: string) => {
    setFiles((prev) => prev.filter((f) => f.url !== url));
    setReadyStems((prev) => prev.filter((s) => s.url !== url));
  };

  const setRole = (url: string, role: StemRole) => {
    setFiles((prev) => prev.map((f) => (f.url === url ? { ...f, role } : f)));
  };

  ;

  ;
  // ---- Split mode ----
  ;

  // ---- Mix/master preset ----
  

  ;
;

  ;

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
      <p className="text-gray-500 mb-8">Mix and master your tracks</p>

      <div className="flex gap-2 mb-8 overflow-x-auto">
        {[
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
            <p className="text-gray-500 text-sm mb-6">Upload your stems one by one for the best result. Only use the Splitter if you don't have stems.</p>

            <div className="space-y-4">
              <div className="flex gap-2">
                
                
              </div>

              <div>
                <label className="block text-sm text-gray-500 mb-2">
                  
                </label>
                <div>
                <label className="block text-sm text-gray-400 mb-2">Vocal space</label>
                <select value={spaceMode} onChange={(e) => setSpaceMode(e.target.value as SpaceMode)} className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm">
                  <option value="studio">Studio — current sound</option>
                  <option value="room">Room — tight and dry</option>
                  <option value="hall">Hall — big and open</option>
                  <option value="cathedral">Cathedral — huge and dark</option>
                  <option value="plate">Plate Shine — glassy bright halo</option>
                </select>
              </div>

              <MixUploader onReady={addFile} />
              <AiMixer stems={readyStems.length ? readyStems : files} />
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

              

              
            </div>
          </div>

          {stage && !processing && stage !== "Done — preview and download" && (
            <p className="text-gray-500 text-sm text-center">{stage}</p>
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
