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
    <div className="mb-8 rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-xl w-full max-w-2xl mx-auto">
      <div className="mb-4 text-center">
        <h2 className="text-xl font-bold text-white">Whether you recorded your vocals in a studio or just on your phone.</h2>
        <p className="text-sm text-slate-400 mt-1">Listen to what WraGstudio does to a 15-second clip.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <button onClick={() => togglePlay("phone")} className={`flex flex-col items-center justify-center rounded-xl p-5 transition-all ${playing === "phone" ? "bg-green-600/20 border-2 border-green-500 text-green-400" : "bg-slate-700 hover:bg-slate-600 border-2 border-transparent text-slate-300"}`}>
          <span className="mb-2 text-2xl">{playing === "phone" ? "⏸️" : "▶️"}</span>
          <span className="font-bold">Phone Recording</span>
          <span className="text-xs opacity-70 mt-1">Mixed by WraGstudio</span>
          <audio ref={phoneRef} src="/demo-phone.mp3" onEnded={() => setPlaying(null)} />
        </button>

        <button onClick={() => togglePlay("studio")} className={`flex flex-col items-center justify-center rounded-xl p-5 transition-all ${playing === "studio" ? "bg-blue-600/20 border-2 border-blue-500 text-blue-400" : "bg-slate-700 hover:bg-slate-600 border-2 border-transparent text-slate-300"}`}>
          <span className="mb-2 text-2xl">{playing === "studio" ? "⏸️" : "▶️"}</span>
          <span className="font-bold">Studio Recording</span>
          <span className="text-xs opacity-70 mt-1">Mixed by WraGstudio</span>
          <audio ref={studioRef} src="/demo-studio.mp3" onEnded={() => setPlaying(null)} />
        </button>
      </div>
    </div>
  );
}
