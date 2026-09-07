"use client";
import { useUser } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useState, Suspense } from "react";
import MixUploader from "@/components/MixUploader";

type StudioTab = "beat" | "cover" | "mix";
type MixType = "stems" | "automix" | "master";
type UploadedFile = { url: string; name: string };
type SplitResult = { name: string; stems: { type: string; url: string }[] };

function getStudioTab(value: string | null): StudioTab {
  return value === "beat" || value === "cover" || value === "mix" ? value : "beat";
}

function StudioInner() {
  const { user } = useUser();
  const searchParams = useSearchParams();
  const initialType = getStudioTab(searchParams.get("type"));

  const [activeTab, setActiveTab] = useState<StudioTab>(initialType);
  const [mixType, setMixType] = useState<MixType>("stems");
  const [mixFiles, setMixFiles] = useState<UploadedFile[]>([]);
  const [mixProcessing, setMixProcessing] = useState(false);
  const [mixStage, setMixStage] = useState("");
  const [splitResults, setSplitResults] = useState<SplitResult[]>([]);

  const addFile = (url: string, name: string) => {
    setMixFiles((prev) => {
      if (prev.some((f) => f.url === url)) return prev;
      return [...prev, { url, name }];
    });
  };

  const removeFile = (url: string) => {
    setMixFiles((prev) => prev.filter((f) => f.url !== url));
    setSplitResults((prev) => prev.filter((r) => r.name !== url));
  };

  const processMix = async () => {
    if (mixType !== "stems") {
      alert(mixType === "automix" ? "Auto Mix engine is next. Stems splitting is live now — pick Split Stems." : "Master engine is next — pick Split Stems for now.");
      return;
    }
    if (!mixFiles.length) {
      alert("Upload at least one audio file first");
      return;
    }

    setMixProcessing(true);
    setMixStage("Splitting track 1 of " + mixFiles.length + "…");
    const results: SplitResult[] = [];

    for (let i = 0; i < mixFiles.length; i++) {
      const f = mixFiles[i];
      setMixStage("Splitting " + f.name + " (" + (i + 1) + "/" + mixFiles.length + ")… free queue can take 1–3 min");
      try {
        const res = await fetch("/api/mix-stems", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audioUrl: f.url }),
        });
        const data = await res.json();
        if (!data.taskId) {
          alert(f.name + " — " + (data.error || "Split failed — check credits"));
          continue;
        }
        let done = false;
        for (let p = 0; p < 60; p++) {
          await new Promise((r) => setTimeout(r, 10000));
          const sres = await fetch("/api/mix-status?hash=" + encodeURIComponent(data.taskId));
          const sdata = await sres.json();
          const st = sdata.status || (sdata.data && sdata.data.status);
          const files = sdata.data && sdata.data.files ? sdata.data.files : sdata.files;
          if (st === "done" && Array.isArray(files)) {
            const stems = files.filter((f: any) => f && f.url).map((f: any) => ({ type: f.type, url: f.url }));
            results.push({ name: f.name, stems });
            done = true;
            break;
          }
          if (st === "failed") {
            alert(f.name + " — split failed on server");
            done = true;
            break;
          }
        }
        if (!done) alert(f.name + " — timed out, try again in a minute");
      } catch (e: any) {
        alert("Error splitting " + f.name + ": " + ((e && e.message) ? e.message : "network error"));
      }
    }

    setSplitResults(results);
    setMixStage("");
    setMixProcessing(false);
  };

  if (!user) return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading…</div>;

  return (
    <div className="min-h-screen bg-white px-4 py-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Studio</h1>
      <p className="text-gray-500 mb-8">Create beats, design covers, or process your tracks</p>

      {/* Tabs */}
      <div className="flex gap-2 mb-8 overflow-x-auto">
        {[
          { id: "beat" as const, label: "🎵 Beat Generator", color: "purple" },
          { id: "cover" as const, label: "🎨 Album Cover", color: "green" },
          { id: "mix" as const, label: "🎛️ Mix & Master", color: "blue" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 rounded-xl font-semibold whitespace-nowrap transition ${
              activeTab === tab.id
                ? "bg-green-500 text-black"
                : "bg-white text-gray-500 hover:text-slate-900 border border-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* MIX & MASTER */}
      {activeTab === "mix" && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl p-6 border border-slate-200">
            <h2 className="text-xl font-bold mb-4">Mix & Master</h2>
            <p className="text-gray-500 text-sm mb-6">Upload your track. Choose what you need.</p>

            <div className="space-y-4">
              {/* Upload Audio — multiple files */}
              <div>
                <label className="block text-sm text-gray-500 mb-2">Upload Audio File (up to 64MB each)</label>
                <MixUploader onReady={addFile} />
                {mixFiles.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {mixFiles.map((f) => (
                      <div key={f.url} className="flex items-center justify-between bg-green-50 border border-green-500/40 rounded-xl p-3">
                        <div className="flex-1 min-w-0">
                          <div className="text-green-700 font-semibold text-sm truncate">✅ {f.name}</div>
                          <audio controls src={f.url} className="w-full mt-1" preload="none" />
                        </div>
                        <button onClick={() => removeFile(f.url)} className="ml-2 text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Processing Type */}
              <div>
                <label className="block text-sm text-gray-500 mb-2">What do you need?</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: "stems" as const, label: "✂️ Split Stems", desc: "Lead • Backing • Instrumental" },
                    { id: "automix" as const, label: "🎛️ Auto Mix", desc: "Professional mix from stems" },
                    { id: "master" as const, label: "🔊 Master", desc: "Polish final track" },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => setMixType(opt.id)}
                      className={`p-3 rounded-xl text-center transition border ${
                        mixType === opt.id
                          ? "bg-green-500/10 border-green-500 text-slate-900"
                          : "bg-white border-slate-200 text-gray-500 hover:text-slate-900"
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
                disabled={mixProcessing || !mixFiles.length}
                className="w-full bg-green-500 hover:bg-green-400 disabled:bg-gray-100 disabled:text-gray-500 text-black font-bold py-4 rounded-xl transition text-lg"
              >
                {mixProcessing ? "Splitting " + mixFiles.length + " tracks… ⏳" : "Split All Tracks (" + mixFiles.length + ") ✂️"}
              </button>
            </div>
          </div>

          {mixStage && (
            <p className="text-gray-500 text-sm text-center">{mixStage}</p>
          )}

          {splitResults.map((r) => (
            <div key={r.name} className="bg-white rounded-2xl p-6 border border-green-500/30">
              <h3 className="font-bold mb-1 text-green-600">✅ {r.name} — stems ready</h3>
              <p className="text-xs text-gray-500 mb-3">{r.stems.length} stem{r.stems.length > 1 ? "s" : ""} — 320 kbps</p>
              <div className="space-y-3">
                {r.stems.map((s) => (
                  <div key={s.type + s.url} className="border border-slate-200 rounded-xl p-3">
                    <div className="font-semibold mb-2">{s.type}</div>
                    <audio controls src={s.url} className="w-full mb-2" preload="none" />
                    <a href={s.url} target="_blank" rel="noreferrer" download className="text-sm font-semibold text-green-600">Download {s.type} ⬇️</a>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Studio() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-500">Loading…</div>}>
      <StudioInner />
    </Suspense>
  );
}
