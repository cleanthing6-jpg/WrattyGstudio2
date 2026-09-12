"use client";
import { useRef, useState } from "react";
import { useUploadThing } from "@/utils/uploadthing";
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

export default function MixUploader({ onReady }: { onReady: (url: string, name: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  void useUploadThing("audioUploader", {
    onClientUploadComplete: (res: any[]) => {
      const f = res && res[0];
      const url = (f && (f.ufsUrl || f.url || (f.serverData && f.serverData.url))) || "";
      if (url) onReady(url, (f && f.name) || "Track");
      else setError("No URL on file: " + JSON.stringify(f).slice(0, 300));
    },
    onUploadError: (e: any) => {
      setError("Upload error: " + ((e && e.message) ? e.message : "unknown"));
    },
  });

  const pick = async (files: FileList | null) => {
    const arr = files ? Array.from(files) : [];
    if (!arr.length) return;
    setError("");
    setBusy(true);
    try {
      for (const file of arr) {
        const res = await startUpload([file]);
        const f: any = (res && res[0]) || {};
        const url = f.ufsUrl || f.url || (f.serverData && f.serverData.url) || "";
        if (!url) throw new Error("No URL returned for " + file.name);
        onReady(url, file.name);
      }
    } catch (e: any) {
      setError("Upload error: " + ((e && e.message) ? e.message : "unknown"));
    }
    setBusy(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div>
      <label className="block border-2 border-dashed border-slate-200 hover:border-gray-500 rounded-xl p-8 text-center cursor-pointer transition">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="audio/*,.m4a,.mp3,.wav,.aac,.ogg,.flac,.mp4"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
        {busy ? (
          <div className="text-gray-400">Uploading… ⏳</div>
        ) : (
          <div>
            <div className="text-3xl mb-2">🎙️</div>
            <div className="text-gray-400">Tap to choose audio files</div>
            <div className="text-gray-600 text-sm">WAV or M4A/MP3 256kbps+ · up to 128MB</div>
            <div className="text-gray-600 text-sm">Full song to split, or stems to mix — lead, backups, ad-libs, beat</div>
          </div>
        )}
      </label>
      {error && <p className="mt-3 text-red-500 text-sm font-semibold break-all">{error}</p>}
    </div>
  );
}
