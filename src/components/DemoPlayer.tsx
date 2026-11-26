"use client";
import { useState, useRef } from "react";

export default function DemoPlayer() {
  const [playing, setPlaying] = useState<"phone" | "studio" | null>(null);
  const phoneRef = useRef<HTMLAudioElement>(null);
  const studioRef = useRef<HTMLAudioElement>(null);

  const togglePlay = (type: "phone" | "studio") => {
    if (type === "phone") {
      if (playing === "phone") {
        phoneRef.current?.pause(); setPlaying(null);
      } else {
        studioRef.current?.pause(); studioRef.current!.currentTime = 0;
        phoneRef.current?.play(); setPlaying("phone");
      }
    } else {
      if (playing === "studio") {
        studioRef.current?.pause(); setPlaying(null);
      } else {
        phoneRef.current?.pause(); phoneRef.current!.currentTime = 0;
        studioRef.current?.play(); setPlaying("studio");
      }
    }
  };

  return (
    <div className="mb-10 rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-2xl w-full max-w-3xl mx-auto">
      <div className="mb-6 text-center">
        <h2 className="text-2xl font-extrabold text-white tracking-tight">Hear the WraGstudio Difference.</h2>
        <p className="text-sm text-slate-400 mt-2">Raw vocals turned into industry-standard records. Listen for yourself.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Phone Track */}
        <button onClick={() => togglePlay("phone")} className={`group flex flex-col items-center justify-center rounded-xl p-6 transition-all duration-200 ${playing === "phone" ? "bg-green-600/20 border-2 border-green-500 shadow-[0_0_15px_rgba(34,197,94,0.3)]" : "bg-slate-700 hover:bg-slate-600 border-2 border-transparent hover:border-slate-500 text-slate-300"}`}>
          <div className={`mb-3 flex h-12 w-12 items-center justify-center rounded-full transition-transform group-hover:scale-110 ${playing === "phone" ? "bg-green-500 text-white" : "bg-slate-600 text-slate-300"}`}>
            {playing === "phone" ? "⏸" : "▶"}
          </div>
          <span className={`font-bold text-lg ${playing === "phone" ? "text-green-400" : "text-white"}`}>Recorded on Phone</span>
          <span className="text-xs font-semibold text-slate-400 mt-1 uppercase tracking-wider">WraGstudio Mix</span>
          <audio ref={phoneRef} src="/demo-phone.mp3" onEnded={() => setPlaying(null)} />
        </button>

        {/* Studio Track */}
        <button onClick={() => togglePlay("studio")} className={`group flex flex-col items-center justify-center rounded-xl p-6 transition-all duration-200 ${playing === "studio" ? "bg-blue-600/20 border-2 border-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)]" : "bg-slate-700 hover:bg-slate-600 border-2 border-transparent hover:border-slate-500 text-slate-300"}`}>
          <div className={`mb-3 flex h-12 w-12 items-center justify-center rounded-full transition-transform group-hover:scale-110 ${playing === "studio" ? "bg-blue-500 text-white" : "bg-slate-600 text-slate-300"}`}>
            {playing === "studio" ? "⏸" : "▶"}
          </div>
          <span className={`font-bold text-lg ${playing === "studio" ? "text-blue-400" : "text-white"}`}>Recorded in Studio</span>
          <span className="text-xs font-semibold text-slate-400 mt-1 uppercase tracking-wider">WraGstudio Mix</span>
          <audio ref={studioRef} src="/demo-studio.mp3" onEnded={() => setPlaying(null)} />
        </button>
      </div>
    </div>
  );
}
