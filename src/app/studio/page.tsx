"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, useEffect, Suspense } from "react";

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = searchParams.get("type") || "beat";

  const [activeTab, setActiveTab] = useState<"beat" | "cover" | "mix">(initialType as any);

  // Beat Generation
  const [beatPrompt, setBeatPrompt] = useState("");
  const [beatDuration, setBeatDuration] = useState("120");
  const [beatGenerating, setBeatGenerating] = useState(false);
  const [beatResult, setBeatResult] = useState("");

  // Cover Generation
  const [coverPrompt, setCoverPrompt] = useState("");
  const [coverGenerating, setCoverGenerating] = useState(false);
  const [coverResult, setCoverResult] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);

  // Mix & Master
  const [mixFile, setMixFile] = useState<File | null>(null);
  const [mixProcessing, setMixProcessing] = useState(false);
  const [mixResult, setMixResult] = useState("");
  const [mixType, setMixType] = useState<"automix" | "master" | "stems">("automix");

  useEffect(() => {
    const type = searchParams.get("type");
    if (type && ["beat", "cover", "mix"].includes(type)) setActiveTab(type as any);
  }, [searchParams]);

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
    } catch { alert("Network error"); }
    setBeatGenerating(false);
  };

  const generateCover = async () => {
    if (!coverPrompt) return;
    setCoverGenerating(true);
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "cover", prompt: coverPrompt }),
      });
      const data = await res.json();
      if (data.url) setCoverResult(data.url);
      else alert(data.error || "Generation failed");
    } catch { alert("Network error"); }
    setCoverGenerating(false);
  };

  const processMix = async () => {
    if (!mixFile) return;
    setMixProcessing(true);
    try {
      const formData = new FormData();
      formData.append("file", mixFile);
      formData.append("type", mixType);
      const res = await fetch("/api/process", { method: "POST", body: formData });
      const data = await res.json();
      if (data.url) setMixResult(data.url);
      else alert(data.error || "Processing failed");
    } catch { alert("Network error"); }
    setMixProcessing(false);
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
                : "bg-gray-900 text-gray-400 hover:text-white border border-gray-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* BEAT GENERATOR */}
      {activeTab === "beat" && (
        <div className="space-y-6">
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="text-xl font-bold mb-4">Generate a Beat</h2>
            <p className="text-gray-500 text-sm mb-6">Describe the beat you want. Be specific about genre, mood, and tempo.</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Beat Description</label>
                <textarea
                  value={beatPrompt}
                  onChange={e => setBeatPrompt(e.target.value)}
                  placeholder="e.g. Afrobeats dancehall 120bpm, heavy bass, joyful vibe, Amapiano log drums..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-green-500 h-24 resize-none"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-2">Duration (seconds)</label>
                <select
                  value={beatDuration}
                  onChange={e => setBeatDuration(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-green-500"
                >
                  <option value="30">30 seconds (preview)</option>
                  <option value="60">60 seconds</option>
                  <option value="120">2 minutes (full beat)</option>
                </select>
              </div>
              <button
                onClick={generateBeat}
                disabled={beatGenerating || !beatPrompt}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-700 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {beatGenerating ? "Generating... ⏳" : "Generate Beat 🎵"}
              </button>
            </div>
          </div>

          {beatResult && (
            <div className="bg-gray-900 rounded-2xl p-6 border border-green-500/30">
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
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="text-xl font-bold mb-4">Design Album Cover</h2>
            <p className="text-gray-500 text-sm mb-6">Describe your vision or upload reference images.</p>

            <div className="space-y-4">
              {/* Upload Reference */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Reference Image (optional)</label>
                <label className="block border-2 border-dashed border-gray-700 hover:border-gray-500 rounded-xl p-8 text-center cursor-pointer transition">
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
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-green-500 h-24 resize-none"
                />
              </div>

              <button
                onClick={generateCover}
                disabled={coverGenerating || !coverPrompt}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-700 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {coverGenerating ? "Generating... ⏳" : "Generate Cover 🎨"}
              </button>
            </div>
          </div>

          {coverResult && (
            <div className="bg-gray-900 rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-3 text-green-400">✅ Cover Generated!</h3>
              <img src={coverResult} alt="Album Cover" className="w-full rounded-xl mb-4" />
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
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="text-xl font-bold mb-4">Mix & Master</h2>
            <p className="text-gray-500 text-sm mb-6">Upload your track. Choose what you need.</p>

            <div className="space-y-4">
              {/* Upload Audio */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">Upload Audio File</label>
                <label className="block border-2 border-dashed border-gray-700 hover:border-gray-500 rounded-xl p-8 text-center cursor-pointer transition">
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={e => setMixFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                  {mixFile ? (
                    <div className="text-green-400">✅ {mixFile.name}</div>
                  ) : (
                    <div>
                      <div className="text-3xl mb-2">🎙️</div>
                      <div className="text-gray-400">Tap to upload audio</div>
                      <div className="text-gray-600 text-sm">MP3, WAV, M4A — stems or full mix</div>
                    </div>
                  )}
                </label>
              </div>

              {mixFile && (
                <div>
                  <audio controls src={URL.createObjectURL(mixFile)} className="w-full" />
                </div>
              )}

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
                          ? "bg-green-500/10 border-green-500 text-white"
                          : "bg-gray-800 border-gray-700 text-gray-400 hover:text-white"
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
                disabled={mixProcessing || !mixFile}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-700 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {mixProcessing ? "Processing... ⏳" : `Process Track ${mixType === "stems" ? "✂️" : mixType === "automix" ? "🎛️" : "🔊"}`}
              </button>
            </div>
          </div>

          {mixResult && (
            <div className="bg-gray-900 rounded-2xl p-6 border border-green-500/30">
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
