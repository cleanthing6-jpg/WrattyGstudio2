"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, useEffect, Suspense } from "react";

function StudioInner() {
  const { user } = useUser();
  const params = useSearchParams();
  const type = params.get("type") || "beat";
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [creditInfo, setCreditInfo] = useState<any>(null);
  const [mixFile, setMixFile] = useState<File | null>(null);

  useEffect(() => { if (user) fetch("/api/credits").then(r => r.json()).then(setCreditInfo); }, [user]);

  const generate = async () => {
    if (!user) return alert("Sign in first");
    if (type === "mix" && !mixFile) return alert("Upload audio first");
    setLoading(true);
    try {
      const body: any = { type, prompt: prompt || "African afrobeats" };
      if (type === "mix" && mixFile) {
        const fd = new FormData();
        fd.append("file", mixFile);
        fd.append("type", "mix");
        const upRes = await fetch("/api/upload-audio", { method: "POST", body: fd });
        const upData = await upRes.json();
        body.audioUrl = upData.url;
      }
      const res = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (data.url) setResult(data.url);
      else alert(data.error || "Failed");
    } catch (e: any) { alert(e.message); }
    setLoading(false);
  };

  return (
    <div className="min-h-screen p-6 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2 capitalize">{type === "beat" ? "Generate Beat" : type === "cover" ? "Design Album Cover" : "Automix & Master"}</h1>
      {creditInfo && <p className="text-gray-400 mb-6">Plan: {creditInfo.tier.toUpperCase()} — {type === "beat" ? "Beats" : type === "cover" ? "Covers" : "Mixes"} left: {type === "beat" ? creditInfo.beats_left : type === "cover" ? creditInfo.covers_left : creditInfo.mixes_left}</p>}
      <textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder={type === "beat" ? "Describe your beat: Afrobeats, 120bpm, heavy drums, melodic keys..." : type === "cover" ? "Describe album cover: Dark background, golden lion, African patterns..." : "Describe your mix style: Loud, punchy, radio-ready..."} className="w-full bg-gray-900 rounded-xl p-4 text-white mb-4 h-32 resize-none" />
      {type === "mix" && <input type="file" accept="audio/*" onChange={e => setMixFile(e.target.files?.[0] || null)} className="w-full bg-gray-900 rounded-xl p-4 text-white mb-4" />}
      <button onClick={generate} disabled={loading} className="bg-green-500 hover:bg-green-600 text-black font-bold py-3 px-8 rounded-full disabled:opacity-50">{loading ? "Generating..." : type === "mix" ? "Mix & Master" : "Generate"}</button>
      {result && (
        <div className="mt-8 bg-gray-900 rounded-xl p-6">
          <p className="text-green-400 font-semibold mb-3">✅ Done! Preview:</p>
          {type === "beat" || type === "cover" ? (
            type === "beat" ? <audio src={result} controls className="w-full" /> : <img src={result} alt="Album Cover" className="w-full rounded-lg" />
          ) : <audio src={result} controls className="w-full" />}
          <a href={result} download className="mt-3 inline-block bg-green-500 text-black font-bold py-2 px-6 rounded-full text-sm">Download</a>
        </div>
      )}
    </div>
  );
}

export default function StudioPage() {
  return <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>}><StudioInner /></Suspense>;
}
