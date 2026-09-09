"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, Suspense, useRef, useCallback } from "react";
import MixUploader from "@/components/MixUploader";
import { useUploadThing } from "@/utils/uploadthing";


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
  const targetRms = 0.22;
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
  limiter.threshold.value = -1;
  limiter.ratio.value = 20;
  limiter.attack.value = 0.001;
  limiter.release.value = 0.12;
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

type StudioTab = "beat" | "cover" | "mix";
type SpaceMode = "studio" | "room" | "hall" | "cathedral" | "plate";
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
  const [spaceMode, setSpaceMode] = useState<SpaceMode>("studio");
  const spaceRef = useRef<SpaceMode>("studio");
  spaceRef.current = spaceMode;
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [splitResults, setSplitResults] = useState<SplitResult[]>([]);
  const [readyStems, setReadyStems] = useState<ReadyStem[]>([]);
  const [processing, setProcessing] = useState(false);
  const [stage, setStage] = useState("");
  const [mixedBlob, setMixedBlob] = useState<Blob | null>(null);
  const { startUpload } = useUploadThing("audioUploader");
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
        if (t.includes("lead") || t.includes("vocal")) role = "lead";
        else if (t.includes("back")) role = "backup";
        else if (t.includes("ad")) role = "adlib";
        else if (t.includes("drum") || t.includes("bass") || t.includes("other") || t.includes("music") || t.includes("accompaniment") || t.includes("instrument")) role = "beat";
        stems.push({ url: s.url, name: s.type, role });
      }
    }
    setReadyStems(stems);
  };

  const clearSplitResults = () => { setSplitResults([]); };
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
    const length = Math.max(1, Math.ceil((mixLen + 2.5) * sampleRate));
    const offline = new OfflineAudioContext(2, length, sampleRate);

    const mixInput = offline.createGain();
    mixInput.gain.value = 1;
        const masterLim = offline.createDynamicsCompressor();
        masterLim.threshold.value = -1;
        masterLim.ratio.value = 20;
        masterLim.attack.value = 0.002;
        masterLim.release.value = 0.15;
        masterLim.knee.value = 0;
    mixInput.connect(masterLim); masterLim.connect(offline.destination);

    // Vocal glue bus (lead + backing bus + adlib bus all sum here)
    const vocalGlue = offline.createGain();
    vocalGlue.gain.value = 1;

    const glueComp = offline.createDynamicsCompressor();
    glueComp.threshold.value = -16;
    glueComp.ratio.value = 2;
    glueComp.attack.value = 0.01;
    glueComp.release.value = 0.2;
    glueComp.knee.value = 8;

    const glueMakeup = offline.createGain();
    glueMakeup.gain.value = 1.25;

    vocalGlue.connect(glueComp);
    glueComp.connect(glueMakeup);
        const glueSat = offline.createWaveShaper();
        glueSat.oversample = "2x";
        const glueSatCurve = new Float32Array(1024);
        for (let gi = 0; gi < 1024; gi++) { const gx = (gi / 511.5) - 1; glueSatCurve[gi] = Math.tanh(1.2 * gx) / Math.tanh(1.2); }
        glueSat.curve = glueSatCurve;
    glueMakeup.connect(glueSat); glueSat.connect(mixInput);

    // Backing bus compressor + makeup
    const backBus = offline.createGain();
    backBus.gain.value = 1;

    const backComp = offline.createDynamicsCompressor();
    backComp.threshold.value = -22;
    backComp.ratio.value = 3.5;
    backComp.attack.value = 0.005;
    backComp.release.value = 0.25;
    backComp.knee.value = 10;

    const backMakeup = offline.createGain();
    backMakeup.gain.value = 1.15;

    backBus.connect(backComp);
    backComp.connect(backMakeup);
    backMakeup.connect(vocalGlue);

    // Adlib bus (quiet, wide, just summed)
    const adlibBus = offline.createGain();
    adlibBus.gain.value = 1;
    adlibBus.connect(vocalGlue);

    // ----- Reverb (stereo IR, exp decay, HP) -----
    const sp = spaceRef.current || "studio"; const spaceCfg = sp === "room" ? { decay: 0.9, damp: 12500, predelay: 0.010, ret: 0.45 } : sp === "hall" ? { decay: 2.2, damp: 9000, predelay: 0.032, ret: 0.55 } : sp === "cathedral" ? { decay: 4.0, damp: 6500, predelay: 0.050, ret: 0.35 } : sp === "plate" ? { decay: 1.5, damp: 16000, predelay: 0.015, ret: 0.6 } : { decay: 0.45, damp: 9000, predelay: 0, ret: 0 };
    const reverb = await loadSpaceIR(sp, offline, spaceCfg);
    const reverbHp = offline.createBiquadFilter();
    reverbHp.type = "highpass";
    reverbHp.frequency.value = 250;
    const reverbReturn = offline.createGain();
    reverbReturn.gain.value = spaceCfg.ret;
        const reverbDamp = offline.createBiquadFilter();
        reverbDamp.type = "lowpass";
        reverbDamp.frequency.value = spaceCfg.damp;
        reverbDamp.Q.value = 0.7;

        const reverbPredelay = offline.createDelay(1.0);
        reverbPredelay.delayTime.value = spaceCfg.predelay;
    reverb.connect(reverbDamp); reverbDamp.connect(reverbHp);
    reverbHp.connect(reverbReturn);
    reverbReturn.connect(mixInput);

    const revSendLead = offline.createGain();
    revSendLead.gain.value = 0.42;
    revSendLead.connect(reverb);
    const revSendBack = offline.createGain();
    revSendBack.gain.value = 0.08;
    revSendBack.connect(reverb);
    const revSendAd = offline.createGain();
    revSendAd.gain.value = 0.05;
    revSendAd.connect(reverb);

    // ----- Ping-pong delay -----
    const delayL = offline.createDelay(1.0);
    delayL.delayTime.value = 0.28;
    const delayR = offline.createDelay(1.0);
    delayR.delayTime.value = 0.34;

    const fbLR = offline.createGain();
    fbLR.gain.value = 0.45;
    const fbRL = offline.createGain();
    fbRL.gain.value = 0.45;
    delayL.connect(fbLR);
    fbLR.connect(delayR);
    delayR.connect(fbRL);
    fbRL.connect(delayL);

    const delayMerge = offline.createChannelMerger(2);
    const delayWetL = offline.createGain();
    delayWetL.gain.value = 0.8;
    const delayWetR = offline.createGain();
    delayWetR.gain.value = 0.8;
    delayL.connect(delayWetL);
    delayWetL.connect(delayMerge, 0, 0);
    delayR.connect(delayWetR);
    delayWetR.connect(delayMerge, 0, 1);
    const delayReturn = offline.createGain();
    delayReturn.gain.value = 1;
    delayMerge.connect(delayReturn);
    delayReturn.connect(mixInput);

    const delaySendLead = offline.createGain();
    delaySendLead.gain.value = 0.45;
    delaySendLead.channelCount = 1;
    delaySendLead.channelCountMode = "explicit";
    delaySendLead.connect(delayL);
    delaySendLead.connect(delayR);

    // ----- Stem loop with role processing -----
    for (let i = 0; i < stems.length; i++) {
      const role = normRole(stems[i].role, (stems[i] as any).name);
      const src = offline.createBufferSource();
      src.buffer = buffers[i];

      if (role === "beat") {
        const g = offline.createGain();
        g.gain.value = 1.5;
        const hp = offline.createBiquadFilter();
        hp.type = "highpass";
        hp.frequency.value = 28;
        src.connect(g);
        g.connect(hp);
        const beatWeight = offline.createBiquadFilter();
        beatWeight.type = "lowshelf";
        beatWeight.frequency.value = 80;
        beatWeight.gain.value = 3.0;

        const beatCarve = offline.createBiquadFilter();
        beatCarve.type = "peaking";
        beatCarve.frequency.value = 3200;
        beatCarve.Q.value = 1.2;
        beatCarve.gain.value = -2.5;
        const beatCarve2 = offline.createBiquadFilter();
        beatCarve2.type = "peaking";
        beatCarve2.frequency.value = 280;
        beatCarve2.Q.value = 1.4;
        beatCarve2.gain.value = -1.0;
        hp.connect(beatWeight); beatWeight.connect(beatCarve); beatCarve.connect(beatCarve2); beatCarve2.connect(mixInput);
        src.start(0);
        continue;
      }

      const g = offline.createGain();
      g.gain.value = role === "lead" ? 0.65 : role === "adlib" ? 0.12 : 0.15;

      const hp = offline.createBiquadFilter();
      hp.type = "highpass";
      hp.frequency.value = role === "lead" ? 70 : role === "adlib" ? 120 : 90;

      const lp = offline.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = role === "lead" ? 16000 : role === "adlib" ? 12000 : 14000;

      const pan = offline.createStereoPanner();
      pan.pan.value = role === "lead" ? 0 : role === "adlib" ? (i % 2 === 0 ? 0.35 : -0.35) : (i % 2 === 0 ? -0.4 : 0.4);

      src.connect(g);
      g.connect(hp);
      hp.connect(lp);

      if (role === "lead") {
        const leadComp = offline.createDynamicsCompressor();
        leadComp.threshold.value = -24;
        leadComp.ratio.value = 3;
        leadComp.attack.value = 0.01;
        leadComp.release.value = 0.12;
        leadComp.knee.value = 8;

        const leadMakeup = offline.createGain();
        leadMakeup.gain.value = 1.15;

        const leadDeess = offline.createBiquadFilter();
        leadDeess.type = "peaking";
        leadDeess.frequency.value = 7200;
        leadDeess.Q.value = 1.6;
        leadDeess.gain.value = -2.5;

        const leadDemud = offline.createBiquadFilter();
        leadDemud.type = "peaking";
        leadDemud.frequency.value = 280;
        leadDemud.Q.value = 0.9;
        leadDemud.gain.value = -2.5;

        const leadAir = offline.createBiquadFilter();
        leadAir.type = "highshelf";
        leadAir.frequency.value = 12000;
        leadAir.gain.value = 1.2;

        const leadBody = offline.createBiquadFilter();
        leadBody.type = "lowshelf";
        leadBody.frequency.value = 160;
        leadBody.gain.value = 0.8;

        const leadPresence = offline.createBiquadFilter();
        leadPresence.type = "peaking";
        leadPresence.frequency.value = 5000;
        leadPresence.Q.value = 0.7;
        leadPresence.gain.value = 1.2;

        lp.connect(leadComp);
        leadComp.connect(leadMakeup);
        leadMakeup.connect(leadDeess);
        leadDeess.connect(leadDemud); leadDemud.connect(leadAir); leadAir.connect(leadBody); leadBody.connect(leadPresence); leadPresence.connect(pan);
      } else {
        lp.connect(pan);
      }

      if (role === "lead") {
        pan.connect(revSendLead);
        pan.connect(delaySendLead);
        pan.connect(vocalGlue);
      } else if (role === "adlib") {
        pan.connect(revSendAd);
        pan.connect(adlibBus);
      } else {
        pan.connect(revSendBack);
        pan.connect(backBus);
      }

      src.start(0);
    }

    const rendered = await offline.startRendering();
    const loudRendered = await loudnessNormalize(rendered);
    return loudRendered;
  }, []);

  const bakeMix = async () => {
    if (mixMode !== "mix") return;
    const stems = readyStems.length ? readyStems : files.map((f) => ({ url: f.url, name: f.name, role: f.role }));
    if (!stems.length) { alert("Upload at least one vocal or beat first"); return; }
    setProcessing(true);
    setStage("Loading & analysing stems...");
    try {
      const result = await applyPreset(stems);
      if (!result) { setProcessing(false); return; }
      const wav = encodeWav(result);
      const blob = new Blob([wav], { type: "audio/wav" });
      setMixedBlob(blob);
      setStage("Uploading master...");
      const beatStem = stems.find((s: any) => s.role === "beat");
      const first = stems[0] as any;
      const base = (beatStem && beatStem.name ? String(beatStem.name) : first && first.name ? String(first.name) : "Mix").replace(/\.[^.]+$/, "");
      const label = base + " - Master";
      let uploadedUrl = "";
      try {
        const up = await startUpload([new File([blob], label + ".wav", { type: "audio/wav" })]);
        const f: any = up && up[0];
        uploadedUrl = (f && (f.ufsUrl || f.url || (f.serverData && f.serverData.url))) || "";
        if (uploadedUrl) {
          try {
            await fetch("/api/mixes", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: label, url: uploadedUrl }),
            });
          } catch (e: any) {
            console.error("DB save error:", e);
          }
        } else {
          console.error("Upload response had no URL (server-side save will catch it):", up);
        }
      } catch (e: any) {
        console.error("Upload error:", e);
      }
      let saved = false;
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        try {
          const res = await fetch("/api/mixes");
          const d = await res.json();
          const list: any[] = d && Array.isArray(d.mixes) ? d.mixes : [];
          if (list.some((m: any) => m.name === label)) { saved = true; break; }
        } catch {}
      }
      setStage(saved ? "Done - saved to dashboard: " + label : "Master ready - it is saving, check Dashboard > My Mixes in a minute");
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
        const dithered = Math.max(-1, Math.min(1, sample + (Math.random() - 0.5) * (1 / 32768)));
        view.setInt16(offset, dithered < 0 ? dithered * 0x8000 : dithered * 0x7FFF, true);
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
            <p className="text-gray-500 text-sm mb-6">Upload your stems one by one for the best result. Only use the Splitter if you don't have stems.</p>

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
                  ✂️ Splitter (only if you don't have stems)
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
                    ? "Upload a full song — we'll split it into Vocals + Instrumental. Backups stay combined inside the vocal stem."
                    : "Upload your stems — lead vocal, backups, ad-libs, and the beat. Label each one."}
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
                        <div className="flex items-center justify-between"><div className="text-xs text-gray-500">Switch to Mix & master preset — roles are assigned automatically.</div><button onClick={() => clearSplitResults()} className="text-red-500 hover:text-red-700 text-sm font-semibold ml-2">Clear ✕</button></div>
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