"use client";
import { useState } from "react";
import { masterStage } from "@/lib/masterStage";

function encodeWav(buf: AudioBuffer): Blob {
  const ch = buf.numberOfChannels;
  const len = buf.length;
  const sr = buf.sampleRate;
  const bytes = len * ch * 2;
  const ab = new ArrayBuffer(44 + bytes);
  const v = new DataView(ab);
  const ws = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) {
      v.setUint8(o + i, s.charCodeAt(i));
    }
  };
  ws(0, "RIFF");
  v.setUint32(4, 36 + bytes, true);
  ws(8, "WAVE");
  ws(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, ch, true);
  v.setUint32(24, sr, true);
  v.setUint32(28, sr * ch * 2, true);
  v.setUint16(32, ch * 2, true);
  v.setUint16(34, 16, true);
  ws(36, "data");
  v.setUint32(40, bytes, true);
  const data: Float32Array[] = [];
  for (let c = 0; c < ch; c++) {
    data.push(buf.getChannelData(c));
  }
  let o = 44;
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < ch; c++) {
      let x = data[c][i];
      if (x > 1) x = 1;
      if (x < -1) x = -1;
      const d = x + (Math.random() - 0.5) / 32768;
      let s = Math.round(d * 32767);
      if (s > 32767) s = 32767;
      if (s < -32768) s = -32768;
      v.setInt16(o, s, true);
      o += 2;
    }
  }
  return new Blob([ab], { type: "audio/wav" });
}

export default function MasterPage() {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("master.wav");
  const [tgt, setTgt] = useState(-10);

  const run = async (f: File) => {
    setBusy(true);
    setUrl("");
    setStage("Reading " + f.name + "...");
    const base = f.name.replace(/\.[^.]+$/, "");
    setName(base + " - Master.wav");
    try {
      const ab = await f.arrayBuffer();
      const w = window as any;
      const AC = w.AudioContext || w.webkitAudioContext;
      const ctx = new AC();
      const buf = await ctx.decodeAudioData(ab);
      setStage("Measuring the song...");
      const out = await masterStage(buf, { targetLUFS: tgt });
      setStage("Writing WAV...");
      const blob = encodeWav(out);
      setUrl(URL.createObjectURL(blob));
      setStage("Done - preview and download");
    } catch (e: any) {
      const m = (e && e.message) || "unknown error";
      setStage("Failed: " + m);
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-[#faf9f4] p-4 text-slate-900">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-black mb-1">Master only</h1>
        <p className="text-slate-500 text-sm mb-6">
          Upload an already-mixed song. No stem processing,
          just the adaptive master stage.
        </p>

        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <label className="block text-sm text-slate-500 mb-2">
            Target loudness
          </label>
          <select
            value={tgt}
            onChange={(e) => setTgt(Number(e.target.value))}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 bg-white text-sm mb-4"
          >
            <option value={-14}>Streaming (-14 LUFS)</option>
            <option value={-10}>Club / field (-10 LUFS)</option>
            <option value={-9}>Loud (-9 LUFS)</option>
            <option value={-8}>Very loud (-8 LUFS)</option>
          </select>

          <input
            type="file"
            accept="audio/*"
            disabled={busy}
            onChange={(e) => {
              const fl = e.target.files;
              const f = fl && fl[0];
              if (f) run(f);
            }}
            className="block w-full text-sm"
          />

          {stage && (
            <p className="mt-4 text-sm text-slate-500">{stage}</p>
          )}
        </div>

        {url && (
          <div className="mt-6 bg-white rounded-2xl border border-slate-200 p-6">
            <p className="font-bold text-green-700 mb-2">
              Master ready
            </p>
            <audio controls src={url} className="w-full" />
            <a
              href={url}
              download={name}
              className="mt-3 inline-block px-5 py-3 rounded-full bg-green-600 text-white font-bold text-sm"
            >
              Download master
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
