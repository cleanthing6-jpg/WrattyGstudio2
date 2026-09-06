"use client";
import { useRef, useState } from "react";
import { useUploadThing } from "@/utils/uploadthing";

export default function MixUploader({ onReady }: { onReady: (url: string, name: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const { startUpload } = useUploadThing("audioUploader", {
    onClientUploadComplete: (res: any[]) => {
      const f = res && res[0];
      const url = (f && (f.ufsUrl || f.url || (f.serverData && f.serverData.url))) || "";
      if (url) {
        onReady(url, (f && f.name) || "Track");
      } else {
        setError("No URL on file: " + JSON.stringify(f).slice(0, 300));
      }
      setBusy(false);
    },
    onUploadError: (e: any) => {
      setError("Upload error: " + ((e && e.message) ? e.message : "unknown"));
      setBusy(false);
    },
  });

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      await startUpload([file]);
    } catch (e: any) {
      setError("Upload error: " + ((e && e.message) ? e.message : "unknown"));
      setBusy(false);
    }
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div>
      <label className="block border-2 border-dashed border-slate-200 hover:border-gray-500 rounded-xl p-8 text-center cursor-pointer transition">
        <input
          ref={inputRef}
          type="file"
          accept="audio/*,.m4a,.mp3,.wav,.aac,.ogg,.flac,.mp4"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
        {busy ? (
          <div className="text-gray-400">Uploading… ⏳</div>
        ) : (
          <div>
            <div className="text-3xl mb-2">🎙️</div>
            <div className="text-gray-400">Tap to choose your audio</div>
            <div className="text-gray-600 text-sm">Any audio file — up to 64MB</div>
          </div>
        )}
      </label>
      {error && <p className="mt-3 text-red-500 text-sm font-semibold break-all">{error}</p>}
    </div>
  );
}
