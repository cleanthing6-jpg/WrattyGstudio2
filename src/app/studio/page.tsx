"use client";
import { useState } from "react";
export default function Studio() {
  const [activeTab, setActiveTab] = useState<"beats" | "covers" | "automix">("beats");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState("");
  const [coverFile, setCoverFile] = useState<File | null>(null);

  async function generateBeat() {
    setLoading(true);
    try {
      const res = await fetch("/api/generate-beat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
      const data = await res.json();
      setResult(data.url || data.error);
    } catch { setResult("Error generating beat"); }
    setLoading(false);
  }

  async function generateCover() {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("prompt", prompt);
      if (coverFile) formData.append("image", coverFile);
      const res = await fetch("/api/generate-cover", { method: "POST", body: formData });
      const data = await res.json();
      setResult(data.url || data.error);
    } catch { setResult("Error generating cover"); }
    setLoading(false);
  }

  async function automix() {
    setLoading(true);
    try {
      const formData = new FormData();
      const input = document.querySelector<HTMLInputElement>("#audio-upload");
      if (input?.files?.[0]) formData.append("audio", input.files[0]);
      const res = await fetch("/api/automix", { method: "POST", body: formData });
      const data = await res.json();
      setResult(data.url || data.error);
    } catch { setResult("Error processing audio"); }
    setLoading(false);
  }

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-4xl font-bold mb-8">Studio</h1>
      <div className="flex gap-4 mb-8">
        {(["beats", "covers", "automix"] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)} className={`px-6 py-2 rounded-full font-bold ${activeTab === t ? "bg-green-500 text-black" : "bg-gray-800 text-gray-400"}`}>
            {t === "beats" ? "Beat Generator" : t === "covers" ? "Album Covers" : "Automix & Master"}
          </button>
        ))}
      </div>
      <div className="bg-gray-900 p-8 rounded-xl max-w-2xl">
        {activeTab === "automix" && <input id="audio-upload" type="file" accept="audio/*" className="mb-4 block text-gray-400" />}
        {activeTab === "covers" && <input type="file" accept="image/*" onChange={(e) => setCoverFile(e.target.files?.[0] || null)} className="mb-4 block text-gray-400" />}
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={activeTab === "beats" ? "Describe your beat..." : activeTab === "covers" ? "Describe your album cover..." : "Upload audio file above..."} className="w-full bg-gray-800 text-white p-4 rounded-lg mb-4 h-32 resize-none" />
        <button onClick={activeTab === "beats" ? generateBeat : activeTab === "covers" ? generateCover : automix} disabled={loading} className="bg-green-500 hover:bg-green-600 text-black font-bold py-3 px-8 rounded-full disabled:opacity-50">
          {loading ? "Processing..." : activeTab === "beats" ? "Generate Beat" : activeTab === "covers" ? "Generate Cover" : "Automix & Master"}
        </button>
        {result && <div className="mt-6 p-4 bg-gray-800 rounded-lg text-green-400 break-all">{result.startsWith("http") ? <a href={result} target="_blank" className="underline">Download Result</a> : result}</div>}
      </div>
    </main>
  );
}
