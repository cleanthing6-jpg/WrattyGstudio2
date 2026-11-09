import Link from "next/link";

export const metadata = {
  title: "Why Adaptive DSP Beats Black-Box AI | WraGstudio",
  description: "Discover why the Idan mix engine (powered by WrattyGstudio) delivers superior audio quality compared to static, black-box AI mastering tools.",
};

export default function WhyAdaptive() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-300 p-8 md:p-16 font-sans">
      <div className="max-w-4xl mx-auto space-y-12">
        <header className="space-y-4">
          <h1 className="text-4xl md:text-5xl font-black text-white">Why Adaptive DSP Beats Black-Box AI</h1>
          <p className="text-xl text-slate-400">Discover how the Idan mix engine makes real-time engineering decisions to protect your music, unlike static AI tools.</p>
        </header>

        <section className="space-y-6">
          <h2 className="text-2xl font-bold text-green-400">1. Stem-Aware Mixing vs. Stereo Processing</h2>
          <p className="text-slate-300 leading-relaxed"><strong>Black-Box AI:</strong> Only accepts a single finished stereo file. It cannot fix a buried vocal, muddy drums, or harsh cymbals without applying a global EQ curve to the entire track.</p>
          <p className="text-slate-300 leading-relaxed"><strong>WraGstudio (Idan mix):</strong> Ingests up to 12 individual stems (lead vocals, adlibs, backings, beat). It applies surgical EQ, compression, and spatial effects to each stem individually before summing them.</p>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-bold text-green-400">2. Dynamic Groove Protection (PLR Guard)</h2>
          <p className="text-slate-300 leading-relaxed"><strong>Black-Box AI:</strong> Forces your track to hit a specific LUFS loudness target, often crushing the transients and killing the punch of the kick drum.</p>
          <p className="text-slate-300 leading-relaxed"><strong>WraGstudio (Idan mix):</strong> Uses a Peak-to-Loudness Ratio (PLR) Guard. If pushing the track louder will drop the PLR below 9.0, the engine <em>refuses</em>. It backs off the loudness to protect the groove and dynamics.</p>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-bold text-green-400">3. Hybrid PSOLA Autotune vs. Basic Pitch Shift</h2>
          <p className="text-slate-300 leading-relaxed"><strong>Black-Box AI:</strong> Does not provide professional pitch correction as part of its automated mastering chain.</p>
          <p className="text-slate-300 leading-relaxed"><strong>WraGstudio (Idan mix):</strong> Includes a dedicated Autotune API. It uses Resplice for subtle shifts and PSOLA for massive shifts, preserving formants so the vocal never sounds robotic.</p>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-bold text-green-400">4. Explainable Telemetry vs. Static Blindness</h2>
          <p className="text-slate-300 leading-relaxed"><strong>Black-Box AI:</strong> You upload a track and get a file back. You have no idea what EQ cuts, compression ratios, or spatial effects were applied.</p>
          <p className="text-slate-300 leading-relaxed"><strong>WraGstudio (Idan mix):</strong> Every render generates a detailed JSON mix report. Developers can read the exact EQ cuts, the PLR guard backup, and the spatial ducking levels.</p>
        </section>

        <div className="pt-8 border-t border-slate-800">
          <p className="text-sm text-slate-500 mb-6">WraGstudio is a product of WrattyGstudio, powered by the Idan mix engine.</p>
          <Link href="/developers" className="inline-block bg-green-600 hover:bg-green-500 text-white font-bold py-3 px-8 rounded-full transition-colors">
            Explore the WraGstudio API
          </Link>
        </div>
      </div>
    </div>
  );
}
