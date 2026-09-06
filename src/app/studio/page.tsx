"use client";
import { useUser } from "@clerk/nextjs";
import MixUploader from "@/components/MixUploader";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useState, Suspense } from "react";

type StudioTab = "beat" | "cover" | "mix";

function getStudioTab(value: string | null): StudioTab {
  return value === "beat" || value === "cover" || value === "mix"
    ? value
    : "beat";
}

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = getStudioTab(searchParams.get("type"));

  const [activeTab, setActiveTab] = useState<StudioTab>(initialType);

  // Beat Generation
  const [beatPrompt, setBeatPrompt] = useState("");
  const [beatDuration, setBeatDuration] = useState("150");
  const [beatGenerating, setBeatGenerating] = useState(false);
  const [beatResult, setBeatResult] = useState("");

  // Cover Generation
  const [coverPrompt, setCoverPrompt] = useState("");
  const [coverGenerating, setCoverGenerating] = useState(false);
  const [coverResult, setCoverResult] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);

  // Mix & Master
  const [mixUrl, setMixUrl] = useState("");
  const [mixName, setMixName] = useState("");
  const [mixStems, setMixStems] = useState<{ type: string; url: string }[]>([]);
  const [mixStage, setMixStage] = useState("");
  const [mixProcessing, setMixProcessing] = useState(false);
  const [mixResult, setMixResult] = useState("");
  const [mixType, setMixType] = useState<"automix" | "master" | "stems">("automix");

  const generateBeat = async () => {
    if (!beatPrompt) return;
    setBeatGenerating(true);
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "beat", prompt: beatPrompt, duration: parseInt(beatDuration) }),
      });
      const data = await res.json();
      if (data.url) setBeatResult(data.url);
      else alert(data.error || "Generation failed");
    } catch (e:any) { alert("Error: " + ((e && e.message) ? e.message : "network error")); }
    setBeatGenerating(false);
  };

const generateCover = async () => {
  if (!coverPrompt) return;
  setCoverGenerating(true);
  try {
    let reference = "";
    if (coverFile) {
      const img = await new Promise<HTMLImageElement>((res, rej) => {
        const el = document.createElement("img");
        el.onload = () => res(el);
        el.onerror = rej;
        el.src = URL.createObjectURL(coverFile);
      });
      const scale = Math.min(1, 512 / Math.max(img.width, img.height));
      const w = Math.max(64, Math.round((img.width * scale) / 64) * 64);
      const h = Math.max(64, Math.round((img.height * scale) / 64) * 64);
      const cv = document.createElement("canvas");
      cv.width = w;
      cv.height = h;
      cv.getContext("2d")!.drawImage(img, 0, 0, w, h);
      reference = cv.toDataURL("image/jpeg", 0.85).split(",")[1];
      URL.revokeObjectURL(img.src);
    }
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "cover", prompt: coverPrompt, reference }),
    });
    const data = await res.json();
    if (data.url) setCoverResult(data.url);
    else alert(data.error || "Generation failed");
  } catch (e:any) { alert("Error: " + ((e && e.message) ? e.message : "network error")); }
  setCoverGenerating(false);
};
  const processMix = async () => {
    if (!mixUrl) return;
    if (mixType === "stems") {
      setMixProcessing(true);
      setMixResult("");
      setMixStems([]);
      try {
        const res = await fetch("/api/mix-stems", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audioUrl: mixUrl }),
        });
        const data = await res.json();
        if (!data.taskId) {
          alert(data.error || "Split failed");
          setMixProcessing(false);
          return;
        }
        for (let i = 0; i < 60; i++) {
          await new Promise((r) => setTimeout(r, 10000));
          const sres = await fetch("/api/mix-status?hash=" + encodeURIComponent(data.taskId));
          const sdata = await sres.json();
          const st = sdata.status || (sdata.data && sdata.data.status);
          const files = sdata.data && sdata.data.files ? sdata.data.files : sdata.files;
          if (st === "done" && Array.isArray(files)) {
            const stems = files
              .filter((f: any) => f && f.url)
              .map((f: any) => ({ type: f.type, url: f.url }));
            if (stems.length) {
              setMixStems(stems);
              setMixProcessing(false);
              return;
            }
          }
          if (st === "failed") {
            alert("Stem split failed on the server");
            setMixProcessing(false);
            return;
          }
        }
        alert("Timed out — free queue is busy, try again in a minute");
        setMixProcessing(false);
      } catch (e: any) {
        alert("Error: " + ((e && e.message) ? e.message : "network error"));
        setMixProcessing(false);
      }
    } else {
      setMixProcessing(false);
      alert(mixType === "automix" ? "Auto Mix engine is next. Stems splitting is live now — pick Split Stems." : "Mastering engine is next. Stems splitting is live now — pick Split Stems.");
    }
  };

  if (!user) return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading...</div>;

  return (
    <div className="min-h-screen px-4 py-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Studio</h1>
      <p className="text-gray-500 mb-8">Create beats, design covers, or process your tracks</p>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 overflow-x-auto">
        {[
          { id: "beat" as const, label: "🎵 Beat Generator", color: "purple" },
          { id: "cover" as const, label: "🎨 Album Cover", color: "pink" },
          { id: "mix" as const, label: "🎛️ Mix & Master", color: "blue" },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 rounded-xl font-semibold whitespace-nowrap transition ${
              activeTab === tab.id
                ? "bg-green-500 text-black"
                : "bg-white text-gray-400 hover:text-slate-900 border border-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* BEAT GENERATOR */}
      {activeTab === "beat" && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200">
            <h2 className="text-xl font-bold mb-4">Generate a Beat</h2>
            <p className="text-gray-500 text-sm mb-6">Describe the beat you want. Be specific about genre, mood, and tempo.</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Beat Description</label>
                <textarea
                  value={beatPrompt}
                  onChange={e => setBeatPrompt(e.target.value)}
                  placeholder="e.g. Afrobeats dancehall 120bpm, heavy bass, joyful vibe, Amapiano log drums..."
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-slate-900 placeholder-gray-600 focus:outline-none focus:border-green-500 h-24 resize-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-2">Duration (seconds)</label>
                <select
                  value={beatDuration}
                  onChange={e => setBeatDuration(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-slate-900 focus:outline-none focus:border-green-500"
                >
                  <option value="150">2:30 (150 seconds)</option>
<option value="180">3:00 (180 seconds)</option>
<option value="210">3:30 (210 seconds)</option>
                </select>
              </div>
              <button
                onClick={generateBeat}
                disabled={beatGenerating || !beatPrompt}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {beatGenerating ? "Generating... ⏳" : "Generate Beat 🎵"}
              </button>
            </div>
          </div>

          {beatResult && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-3 text-green-400">✅ Beat Generated!</h3>
              <audio controls src={beatResult} className="w-full mb-4" />
              <a href={beatResult} download className="block w-full text-center bg-green-500 text-black font-bold py-3 rounded-xl">
                Download Beat ⬇️
              </a>
            </div>
          )}
        </div>
      )}

      {/* ALBUM COVER */}
      {activeTab === "cover" && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200">
            <h2 className="text-xl font-bold mb-4">Design Album Cover</h2>
            <p className="text-gray-500 text-sm mb-6">Describe your vision or upload reference images.</p>

            <div className="space-y-4">
              {/* Upload Reference */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Reference Image (optional)</label>
                <label className="block border-2 border-dashed border-slate-200 hover:border-gray-500 rounded-xl p-8 text-center cursor-pointer transition">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={e => setCoverFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                  {coverFile ? (
                    <div className="text-green-400">✅ {coverFile.name}</div>
                  ) : (
                    <div>
                      <div className="text-3xl mb-2">📷</div>
                      <div className="text-gray-400">Tap to upload reference image</div>
                      <div className="text-gray-600 text-sm">JPG, PNG up to 10MB</div>
                    </div>
                  )}
                </label>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Describe Your Cover</label>
                <textarea
                  value={coverPrompt}
                  onChange={e => setCoverPrompt(e.target.value)}
                  placeholder="e.g. African sunset with golden microphone, colorful, vibrant, album art style..."
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-slate-900 placeholder-gray-600 focus:outline-none focus:border-green-500 h-24 resize-none"
                />
              </div>

              <button
                onClick={generateCover}
                disabled={coverGenerating || !coverPrompt}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {coverGenerating ? "Generating... ⏳" : "Generate Cover 🎨"}
              </button>
            </div>
          </div>

          {coverResult && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-3 text-green-400">✅ Cover Generated!</h3>
              <Image src={coverResult} alt="Album Cover" width={1024} height={1024} className="w-full rounded-xl mb-4" unoptimized />
              <a href={coverResult} download className="block w-full text-center bg-green-500 text-black font-bold py-3 rounded-xl">
                Download Cover ⬇️
              </a>
            </div>
          )}
        </div>
      )}

      {/* MIX & MASTER */}
      {activeTab === "mix" && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200">
            <h2 className="text-xl font-bold mb-4">Mix & Master</h2>
            <p className="text-gray-500 text-sm mb-6">Upload your track. Choose what you need.</p>

            <div className="space-y-4">
              {/* Upload Audio */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Upload Audio File (up to 64MB)</label>
                <MixUploader onReady={(url, name) => { setMixUrl(url); setMixName(name); }} />
                {mixUrl && (
                  <div className="mt-3 bg-green-50 border border-green-500/40 rounded-xl p-3">
                    <div className="text-green-600 font-semibold text-sm mb-2">✅ {mixName} uploaded — ready to split</div>
                    <audio controls src={mixUrl} className="w-full" />
                  </div>
                )}
              </div>

              {/* Processing Type */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">What do you need?</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "stems" as const, label: "✂️ Split Stems", desc: "Separate vocals, drums, bass" },
                    { id: "automix" as const, label: "🎛️ Auto Mix", desc: "Professional mix from stems" },
                    { id: "master" as const, label: "🔊 Master", desc: "Polish final track" },
                  ].map(opt => (
                    <button
                      key={opt.id}
                      onClick={() => setMixType(opt.id)}
                      className={`p-3 rounded-xl text-center transition border ${
                        mixType === opt.id
                          ? "bg-green-500/10 border-green-500 text-slate-900"
                          : "bg-white border-slate-200 text-gray-400 hover:text-slate-900"
                      }`}
                    >
                      <div className="font-semibold text-sm">{opt.label}</div>
                      <div className="text-xs mt-1 opacity-60">{opt.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={processMix}
                disabled={mixProcessing || !mixUrl}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {mixProcessing ? "Processing... ⏳" : `Process Track ${mixType === "stems" ? "✂️" : mixType === "automix" ? "🎛️" : "🔊"}`}
              </button>
            </div>
          </div>

          {mixStage && (
            <p className="text-gray-500 text-sm text-center mt-2">{mixStage}</p>
          )}

          {mixStems.length > 0 && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-1 text-green-400">✅ Vocals & Beat Ready!</h3>
              <p className="text-xs text-gray-500 mb-3">Vocals isolated — your beat kept fully intact</p>
              <div className="space-y-3">
                {mixStems.map(s => (
                  <div key={s.type} className="border border-slate-200 rounded-xl p-3">
                    <div className="font-semibold mb-2">{s.type}</div>
                    <audio controls src={s.url} className="w-full mb-2" preload="none" />
                    <a href={s.url} target="_blank" rel="noreferrer" download className="text-sm font-semibold text-green-600">Download {s.type} ⬇️</a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {mixResult && (
            <div className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-3 text-green-400">✅ Processing Complete!</h3>
              <audio controls src={mixResult} className="w-full mb-4" />
              <a href={mixResult} download className="block w-full text-center bg-green-500 text-black font-bold py-3 rounded-xl">
                Download Result ⬇️
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Studio() {
  return <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-500">Loading...</div>}><StudioInner /></Suspense>;
}
