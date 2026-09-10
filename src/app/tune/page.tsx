"use client";

import { useRef, useState } from "react";
import { analyseTrack, buildCurve, detectKey, DEFAULTS, NOTE_NAMES } from "@/lib/tuner/pitch";
import type { Mode, TuneSettings } from "@/lib/tuner/pitch";
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
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState("");
  const [origUrl, setOrigUrl] = useState("");
  const [tunedUrl, setTunedUrl] = useState("");
  const [root, setRoot] = useState(DEFAULTS.root);
  const [mode, setMode] = useState<Mode>(DEFAULTS.mode);
  const [amount, setAmount] = useState(90);
  const [retuneMs, setRetuneMs] = useState(DEFAULTS.retuneMs);
  const [vibrato, setVibrato] = useState(DEFAULTS.vibrato);
  const [busy, setBusy] = useState(false);

  const tune = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { setStatus("Pick a vocal file first"); return; }
    setBusy(true);
    try {
      setStatus("Decoding…");
      const ab = await f.arrayBuffer();
      const AC: any = (window as any).AudioContext || (window as any).webkitAudioContext;
      const ctx = new AC();
      const buf: AudioBuffer = await ctx.decodeAudioData(ab.slice(0));
      const sr = buf.sampleRate;
      const channels: Float32Array[] = [];
      for (let c = 0; c < Math.min(2, buf.numberOfChannels); c++) {
        channels.push(Float32Array.from(buf.getChannelData(c)));
      }
      await ctx.close();

      setStatus("Analysing pitch…");
      await new Promise((r) => setTimeout(r, 0));
      const a = analyseTrack(channels[0], sr);

      setStatus("Building curve…");
      const detRes = detectKey(a, sr);
      const keyOk = detRes.confidence >= 0.35;
      const useRoot = keyOk ? detRes.root : root;
      const useMode = keyOk ? detRes.mode : mode;
      setRoot(useRoot); setMode(useMode);
      setStatus("Auto key: " + NOTE_NAMES[useRoot] + " " + useMode + (keyOk ? " (" + Math.round(detRes.confidence * 100) + "% confident)" : " - low confidence, using your pick"));
      const settings: TuneSettings = { root: useRoot, mode: useMode, amount: amount / 100, retuneMs, vibrato };
      const curve = buildCurve(a, sr, settings);

      setStatus("Tuning — this takes a few seconds…");
      await new Promise((r) => setTimeout(r, 0));
      const tuned = limitPeak(applyCurve(channels, sr, a.hop, curve, a.midi));

      setStatus("Writing WAVs…");
      if (origUrl) URL.revokeObjectURL(origUrl);
      if (tunedUrl) URL.revokeObjectURL(tunedUrl);
      setOrigUrl(URL.createObjectURL(encodeWav(channels, sr)));
      setTunedUrl(URL.createObjectURL(encodeWav(tuned, sr)));
      setStatus("Done — compare below");
    } catch (e: any) {
      setStatus("Failed: " + (e?.message || "unknown error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl p-6 space-y-4">
      <h1 className="text-xl font-bold">Vocal tuner test</h1>
      <input ref={fileRef} type="file" accept="audio/*" className="block text-sm" />
      <div className="flex gap-4">
        <label className="text-sm">Key
          <select value={root} onChange={(e) => setRoot(Number(e.target.value))} className="ml-2 border rounded px-2 py-1">
            {NOTE_NAMES.map((n, i) => (<option key={n} value={i}>{n}</option>))}
          </select>
        </label>
        <label className="text-sm">Scale
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} className="ml-2 border rounded px-2 py-1">
            <option value="minor">minor</option>
            <option value="major">major</option>
            <option value="chromatic">chromatic</option>
          </select>
        </label>
      </div>
      <label className="block text-sm">Strength {amount}%
        <input type="range" min={0} max={100} value={amount} onChange={(e) => setAmount(Number(e.target.value))} className="w-full" />
      </label>
      <label className="block text-sm">Retune {retuneMs} ms
        <input type="range" min={5} max={120} value={retuneMs} onChange={(e) => setRetuneMs(Number(e.target.value))} className="w-full" />
      </label>
      <label className="block text-sm">Vibrato kept {Math.round(vibrato * 100)}%
        <input type="range" min={0} max={100} value={vibrato * 100} onChange={(e) => setVibrato(Number(e.target.value) / 100)} className="w-full" />
      </label>
      <button onClick={tune} disabled={busy} className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-gray-300">
        {busy ? "Working…" : "Tune vocal"}
      </button>
      {status && <p className="text-xs text-gray-600">{status}</p>}
      {origUrl && (
        <div>
          <p className="text-xs font-semibold">Original</p>
          <audio controls src={origUrl} className="w-full" />
        </div>
      )}
      {tunedUrl && (
        <div>
          <p className="text-xs font-semibold">Tuned</p>
          <audio controls src={tunedUrl} className="w-full" />
          <a href={tunedUrl} download="tuned.wav" className="mt-1 inline-block text-xs text-blue-600 underline">Download tuned WAV</a>
        </div>
      )}
    </div>
  );
}
