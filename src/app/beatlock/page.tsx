"use client";
import { useState } from "react";
import { beatLockedMix, gateVocal } from "@/lib/beatLock";
import { masterStage } from "@/lib/masterStage";
import { useUploadThing } from "@/utils/uploadthing";

function encodeWav(buf: AudioBuffer): Blob {
  const ch = buf.numberOfChannels;
  const n = buf.length;
  const sr = buf.sampleRate;
  const bytes = n * ch * 2;
  const ab = new ArrayBuffer(44 + bytes);
  const v = new DataView(ab);
  const ws = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
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
  const d: Float32Array[] = [];
  for (let c = 0; c < ch; c++) d.push(buf.getChannelData(c));
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      let x = d[c][i];
      if (x > 1) x = 1;
      if (x < -1) x = -1;
      const t = x + (Math.random() - 0.5) / 32768;
      let s = Math.round(t * 32767);
      if (s > 32767) s = 32767;
      if (s < -32768) s = -32768;
      v.setInt16(o, s, true);
      o += 2;
    }
  }
  return new Blob([ab], { type: "audio/wav" });
}

async function dec(f: File): Promise<AudioBuffer> {
  const ab = await f.arrayBuffer();
  const w = window as any;
  const AC = w.AudioContext || w.webkitAudioContext;
  const c = new AC();
  return await c.decodeAudioData(ab);
}

export default function BeatLockPage() {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [url, setUrl] = useState("");
  const [vdb, setVdb] = useState(-6);
  const { startUpload } = useUploadThing("audioUploader");
  const [beat, setBeat] = useState<AudioBuffer | null>(null);
  const [voc, setVoc] = useState<AudioBuffer | null>(null);
  const [bName, setBName] = useState("");
  const [vName, setVName] = useState("");

  const pick = async (f: File, which: string) => {
    setStage("Reading " + f.name + "...");
    try {
      const b = await dec(f);
      if (which === "beat") {
        setBeat(b);
        setBName(f.name + " | " + b.duration.toFixed(1) + "s");
      } else {
        setVoc(b);
        setVName(f.name + " | " + b.duration.toFixed(1) + "s");
      }
      setStage("Loaded.");
    } catch (e: any) {
      setStage("Could not read that file: " + (e?.message || "unknown"));
    }
  };

  const run = async () => {
    if (!beat || !voc) {
      setStage("Load a beat and a vocal first");
      return;
    }
    setBusy(true);
    setUrl("");
    setStage("Mixing - beat untouched, vocal processed...");
    try {
      const clean = gateVocal(voc);
      const out = await beatLockedMix(beat, clean, { vocalDb: vdb });
      setStage("Mastering...");
      const mastered = await masterStage(out, { targetLUFS: -11 });
      const blob = new Blob([encodeWav(mastered)], { type: "audio/wav" });
      setUrl(URL.createObjectURL(blob));
      setStage("Saving to dashboard...");
      try {
        const label=(vName||"BeatLock").replace(/\.[^.]+$/,"")+" - Master";
        const up=await startUpload([new File([blob],label+".wav",{type:"audio/wav"})]);
        const f:any=up&&up[0];const fileUrl=(f&&(f.ufsUrl||f.url))||"";
        if(fileUrl){
          const res=await fetch("/api/mixes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:label,url:fileUrl})});
          setStage(res.ok?"Done - mastered & saved: "+label:"Done - mastered (save failed, use Download)");
        }else{setStage("Done - mastered (upload failed, use Download)");}
      }catch(err:any){setStage("Done - mastered (save error, use Download)");}
    } catch (e: any) {
      setStage("Failed: " + (e?.message || "unknown"));
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-[#faf9f4] p-4 text-slate-900">
      <div className="max-w-xl mx-auto">
        <h1 className="text-2xl font-black">Beat-Locked Mix</h1>
        <p className="text-sm text-slate-500 mt-1">
          Your beat is never processed. Only the vocal is.
        </p>

        <div className="mt-5 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-bold text-slate-500">
            1. BEAT - passes through untouched
          </p>
          <input
            type="file"
            accept="audio/*"
            className="mt-2 text-sm"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) pick(f, "beat");
            }}
          />
          <p className="mt-1 text-xs text-green-700">{bName || "no beat loaded"}</p>

          <p className="mt-4 text-xs font-bold text-slate-500">
            2. VOCAL - gets the full chain
          </p>
          <input
            type="file"
            accept="audio/*"
            className="mt-2 text-sm"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) pick(f, "vocal");
            }}
          />
          <p className="mt-1 text-xs text-green-700">{vName || "no vocal loaded"}</p>

          <label className="mt-4 block text-xs font-bold text-slate-500">
            Vocal level: {vdb} dB
          </label>
          <input
            type="range"
            min={-12}
            max={0}
            step={0.5}
            value={vdb}
            onChange={(e) => setVdb(Number(e.target.value))}
            className="w-full"
          />

          <button
            onClick={run}
            disabled={busy}
            className="mt-4 w-full rounded-xl bg-green-600 px-4 py-3 text-sm font-bold text-white disabled:bg-slate-300"
          >
            {busy ? "Working..." : "Render Beat-Locked mix"}
          </button>

          <p className="mt-2 text-xs text-slate-500">{stage}</p>
        </div>

        {url && (
          <div className="mt-5 bg-white rounded-2xl border border-slate-200 p-4">
            <p className="text-sm font-bold text-green-700">Beat untouched - listen</p>
            <audio controls src={url} className="mt-2 w-full" />
            <a
              href={url}
              download="beatlocked.wav"
              className="mt-3 inline-block rounded-xl bg-black px-4 py-2 text-sm font-bold text-white"
            >
              Download WAV
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
