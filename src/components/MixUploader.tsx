"use client";
import { useRef, useState } from "react";

function sanitizeName(name: string): string {
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  const base = (dot >= 0 ? name.slice(0, dot) : name)
    .replace(/[^A-Za-z0-9._-]/g, "_")
    .slice(0, 60);
  return `${base || "stem"}${ext}`;
}

async function uploadToR2(file: File): Promise<string> {
  const type = file.type || "application/octet-stream";

  const res = await fetch("/api/upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: sanitizeName(file.name), type }),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error("Could not get upload URL: " + res.status + " " + (await res.text()).slice(0, 200));
  }
  const { url, getUrl } = await res.json();
  if (!url || !getUrl) throw new Error("No upload URL returned");

  const put = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": type },
    body: file,
  });
  if (!put.ok) {
    throw new Error("R2 upload failed: " + put.status + " " + (await put.text()).slice(0, 200));
  }

  return getUrl as string;
}

export default function MixUploader({ onReady }: { onReady: (url: string, name: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const pick = async (files: FileList | null) => {
    const arr = files ? Array.from(files) : [];
    if (!arr.length) return;
    setError("");
    setBusy(true);
    try {
      for (const file of arr) {
        const url = await uploadToR2(file);
        onReady(url, file.name);
      }
    } catch (e: any) {
      setError("Upload error: " + (e && e.message ? e.message : "unknown"));
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
