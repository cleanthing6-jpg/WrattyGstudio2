"use client";

import { useRef, useState } from "react";
import { analyseTrack, buildCurve, detectKey, DEFAULTS, NOTE_NAMES } from "@/lib/tuner/pitch";
import type { KeyDetection, Mode, TuneSettings } from "@/lib/tuner/pitch";
import { applyCurve, limitPeak } from "@/lib/tuner/shift";

function encodeWav(channels: Float32Array[], sampleRate: number): Blob {
  const ch = channels.length;
  const len = channels[0]?.length ?? 0;
  const blockAlign = ch * 2;
  const dataSize = len * blockAlign;
  const ab = new ArrayBuffer(44 + dataSize);
  const v = new DataView(ab);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + dataSize, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, ch, true); v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * blockAlign, true); v.setUint16(32, blockAlign, true);
  v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, dataSize, true);
  let off = 44;
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < ch; c++) {
      let s = channels[c][i];
      if (s > 1) s = 1; else if (s < -1) s = -1;
      v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
  }
  return new Blob([ab], { type: "audio/wav" });
}

export default function TunePage() {
  const beatRef = useRef<HTMLInputElement | null>(null);
  const vocalRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");
  const [origUrl, setOrigUrl] = useState("");
  const [tunedUrl, setTunedUrl] = useState("");
  const [root, setRoot] = useState(DEFAULTS.root);
  const [mode, setMode] = useState<Mode>(DEFAULTS.mode);
  const [amount, setAmount] = useState(90);
  const [retuneMs, setRetuneMs] = useState(DEFAULTS.retuneMs);
  const [vibrato, setVibrato] = useState(DEFAULTS.vibrato);
  const [busy, setBusy] = useState(false);
  const [det, setDet] = useState<KeyDetection | null>(null);
  const [detSource, setDetSource] = useState("");

  const decode = async (input: HTMLInputElement | null) => {
    const f = input?.files?.[0];
    if (!f) return null;
    const ab = await f.arrayBuffer();
    const AC: any = (window as any).AudioContext || (window as any).webkitAudioContext;
    const ctx = new AC();
    const buf: AudioBuffer = await ctx.decodeAudioData(ab.slice(0));
    const sr = buf.sampleRate;
    const channels: Float32Array[] = [];
    for (let c = 0; c < Math.min(2, buf.numberOfChannels); c++) channels.push(Float32Array.from(buf.getChannelData(c)));
    await ctx.close();
    return { channels, sr };
  };

  const keyFrom = async (input: HTMLInputElement | null, label: string) => {
    const d = await decode(input);
    if (!d) return null;
    const a = analyseTrack(d.channels[0], d.sr);
    const k = detectKey(a, d.sr);
    setDet(k); setDetSource(label); setRoot(k.root); setMode(k.mode);
    return k;
  };

  const detect = async () => {
    if (busy) return;
    setBusy(true); setErr(""); setStatus(""); setDet(null); setDetSource("");
    try {
      const bEl = beatRef.current;
      const hasBeat = !!(bEl && bEl.files && bEl.files[0]);
      const el = hasBeat ? bEl : vocalRef.current;
      const label = hasBeat ? "beat" : "vocal";
      if (!el || !el.files || !el.files[0]) throw new Error("Add a beat or a vocal file first");
      setStatus("Detecting the key from the " + label + "…");
      await new Promise((r) => setTimeout(r, 0));
      const k = await keyFrom(el, label);
      if (!k) throw new Error("Could not read that file");
      setStatus("Key from the " + label + ": " + NOTE_NAMES[k.root] + " " + k.mode + " (" + Math.round(k.confidence * 100) + "% confident)");
    } catch (e: any) {
      setErr(e?.message || "Detect failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  };

  const tune = async (o?: { amount?: number; retuneMs?: number; vibrato?: number }) => {
    if (busy) return;
    setBusy(true); setErr(""); setStatus("");
    try {
      const vEl = vocalRef.current;
      if (!vEl || !vEl.files || !vEl.files[0]) throw new Error("Add the lead vocal file");

      let useRoot = root;
      let useMode: Mode = mode;
      const bEl = beatRef.current;
      const hasBeat = !!(bEl && bEl.files && bEl.files[0]);

      if (hasBeat) {
        setStatus("Reading the beat for the key…");
        await new Promise((r) => setTimeout(r, 0));
        const k = await keyFrom(bEl, "beat");
        if (k) { useRoot = k.root; useMode = k.mode; }
      } else if (!det) {
        setStatus("Reading the vocal for the key…");
        await new Promise((r) => setTimeout(r, 0));
        const k = await keyFrom(vEl, "vocal");
        if (k && k.confidence >= 0.3) { useRoot = k.root; useMode = k.mode; }
      }

      setStatus("Decoding vocal…");
      const vd = await decode(vEl);
      if (!vd) throw new Error("Could not read the vocal file");
      setStatus("Analysing vocal pitch…");
      await new Promise((r) => setTimeout(r, 0));
      const a = analyseTrack(vd.channels[0], vd.sr);

      const amt = (o?.amount ?? amount) / 100;
      const rt = o?.retuneMs ?? retuneMs;
      const vib = o?.vibrato ?? vibrato;
      setStatus("Tuning the vocal in " + NOTE_NAMES[useRoot] + " " + useMode + "…");
      const settings: TuneSettings = { root: useRoot, mode: useMode, amount: amt, retuneMs: rt, vibrato: vib };
      const curve = buildCurve(a, vd.sr, settings);
      const out = limitPeak(applyCurve(vd.channels, vd.sr, a.hop, curve, a.midi));

      setOrigUrl(URL.createObjectURL(encodeWav(vd.channels, vd.sr)));
      setTunedUrl(URL.createObjectURL(encodeWav(out, vd.sr)));
      setStatus("Done — vocal tuned to " + NOTE_NAMES[useRoot] + " " + useMode + ". Compare below.");
    } catch (e: any) {
      setErr(e?.message || "Tune failed");
      setStatus("");
    } finally {
      setBusy(false);
    }
  };

  const autoTune = async () => {
    const rt = DEFAULTS.retuneMs;
    const vib = DEFAULTS.vibrato;
    setAmount(90); setRetuneMs(rt); setVibrato(vib);
    await tune({ amount: 90, retuneMs: rt, vibrato: vib });
  };

  return (
    <div className="mx-auto max-w-xl p-4">
      <h1 className="text-xl font-bold mb-1">Vocal Tuner</h1>
      <p className="text-xs text-gray-500 mb-4">The beat sets the key. The vocal gets tuned to it. Output length matches the input exactly.</p>

      <label className="block text-xs font-semibold text-gray-600 mb-1">1. Beat / instrumental — sets the key</label>
      <input ref={beatRef} type="file" accept="audio/*" className="w-full mb-1 text-xs" />
      <p className="text-[11px] text-gray-400 mb-3">Bass and chords state the key plainly. Skip this only if you have no beat.</p>

      <label className="block text-xs font-semibold text-gray-600 mb-1">2. Lead vocal — this is what gets tuned</label>
      <input ref={vocalRef} type="file" accept="audio/*" className="w-full mb-3 text-xs" />

      <div className="flex gap-2 mb-3">
        <button onClick={detect} disabled={busy} className="flex-1 rounded-lg bg-blue-600 px-3 py-3 text-sm font-semibold text-white disabled:bg-gray-300">
          🔍 Auto-detect key
        </button>
        <button onClick={autoTune} disabled={busy} className="flex-1 rounded-lg bg-black px-3 py-3 text-sm font-semibold text-white disabled:bg-gray-300">
          ✨ Auto-Tune
        </button>
      </div>

      {det && (
        <div className="mb-3 rounded-lg border border-green-300 bg-green-50 p-3">
          <p className="text-sm font-bold text-green-800">
            Detected: {NOTE_NAMES[det.root]} {det.mode} — {Math.round(det.confidence * 100)}% confident
          </p>
          {detSource ? <p className="text-[11px] text-green-700">Source: the {detSource}</p> : null}
          {det.runnerUp ? <p className="text-[11px] text-green-700">Next best: {NOTE_NAMES[det.runnerUp.root]} {det.runnerUp.mode}</p> : null}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">Key</label>
          <select value={root} onChange={(e) => setRoot(Number(e.target.value))} className="w-full rounded-lg border border-gray-300 px-2 py-2 text-sm">
            {NOTE_NAMES.map((n, i) => (<option key={n} value={i}>{n}</option>))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-600 mb-1">Scale</label>
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} className="w-full rounded-lg border border-gray-300 px-2 py-2 text-sm">
            <option value="minor">minor</option>
            <option value="major">major</option>
            <option value="chromatic">chromatic</option>
          </select>
        </div>
      </div>

      <label className="block text-xs font-semibold text-gray-600 mb-1">Strength — {amount}%</label>
      <input type="range" min={0} max={100} value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="w-full mb-2" />

      <label className="block text-xs font-semibold text-gray-600 mb-1">Retune — {retuneMs} ms</label>
      <input type="range" min={5} max={120} value={retuneMs} onChange={(e) => setRetuneMs(Number(e.target.value))} className="w-full mb-2" />

      <label className="block text-xs font-semibold text-gray-600 mb-1">Vibrato kept — {Math.round(vibrato * 100)}%</label>
      <input type="range" min={0} max={100} value={Math.round(vibrato * 100)} onChange={(e) => setVibrato(Number(e.target.value) / 100)} className="w-full mb-3" />

      <button onClick={() => tune()} disabled={busy} className="w-full rounded-lg bg-blue-700 px-4 py-3 text-sm font-semibold text-white disabled:bg-gray-300 mb-3">
        {busy ? "Working…" : "🎤 Tune vocal to the beat key"}
      </button>

      {status && <p className="text-xs text-blue-700 mb-1">{status}</p>}
      {err && <p className="text-xs font-semibold text-red-600 mb-1">⚠️ {err}</p>}
      {busy && <p className="text-[11px] text-gray-400 mb-2">Runs on your phone — a long vocal takes a few seconds.</p>}

      {origUrl && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-600 mb-1">Original vocal</p>
          <audio controls src={origUrl} className="w-full" />
        </div>
      )}
      {tunedUrl && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-600 mb-1">Tuned vocal</p>
          <audio controls src={tunedUrl} className="w-full" />
          <a href={tunedUrl} download="tuned.wav" className="mt-1 inline-block text-xs text-blue-600 underline">Download tuned WAV</a>
        </div>
      )}
    </div>
  );
}
