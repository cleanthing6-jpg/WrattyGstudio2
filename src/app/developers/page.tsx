"use client";

import { useState, useEffect } from "react";
import { useUser, SignInButton } from "@clerk/nextjs";

const CodeBlock = ({ code, language }: { code: string; language: string }) => {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative mt-4 rounded-xl overflow-hidden bg-[#0d1117] border border-slate-800">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-800">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{language}</span>
        <button onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); }} className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1">
          {copied ? "✅ Copied!" : "📋 Copy"}
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="text-sm text-[#c9d1d9] font-mono leading-relaxed"><code>{code}</code></pre>
      </div>
    </div>
  );
};

export default function DeveloperDocs() {
  const { isLoaded, isSignedIn, user } = useUser();
  const [keys, setKeys] = useState<any[]>([]);
  const [profile, setProfile] = useState<any>(null);
  
  // Region state
  const [region, setRegion] = useState<"NG" | "INTL">("NG");

  const [buying, setBuying] = useState<"mix" | "master" | null>(null);
  const [buyingCrypto, setBuyingCrypto] = useState<"mix" | "master" | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [copiedKey, setCopiedKey] = useState(false);
  
  const [companyName, setCompanyName] = useState("");
  const [website, setWebsite] = useState("");
  const [formError, setFormError] = useState("");
  const [submittingForm, setSubmittingForm] = useState(false);

  const [supportSubject, setSupportSubject] = useState("");
  const [supportMessage, setSupportMessage] = useState("");
  const [supportStatus, setSupportStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [supportError, setSupportError] = useState("");

  useEffect(() => {
    // Fetch region
    fetch("/api/region").then((r) => r.json()).then((d) => {
      if (d.region === "INTL") setRegion("INTL");
    }).catch(() => {});

    if (isSignedIn) {
      fetch("/api/developer/keys").then((res) => res.json()).then((data) => setKeys(data.keys));
      fetch("/api/developer/profile").then((res) => res.json()).then((data) => {
        if (data.profile) setProfile(data.profile);
      });
    }
  }, [isSignedIn]);

  const submitVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setSubmittingForm(true);
    try {
      const res = await fetch("/api/developer/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ companyName, website })
      });
      const data = await res.json();
      if (res.ok) setProfile({ companyName, website });
      else setFormError(data.error || "Failed to verify");
    } catch (err) {
      setFormError("Network error occurred.");
    } finally {
      setSubmittingForm(false);
    }
  };

  const buyCredits = async (packageType: "mix" | "master") => {
    setBuying(packageType);
    setErrorMsg("");
    try {
      const res = await fetch("/api/developer/buy", { 
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ packageType })
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
      else {
        setErrorMsg(data.error || "Failed to connect to Paystack.");
        setBuying(null);
      }
    } catch (err: any) {
      setErrorMsg("Network error. Please try again.");
      setBuying(null);
    }
  };

  const buyCrypto = async (packageType: "mix" | "master") => {
    setBuyingCrypto(packageType);
    setErrorMsg("");
    try {
      const res = await fetch("/api/developer/buy-crypto", { 
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ packageType })
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
      else {
        setErrorMsg(data.error || "Failed to connect to Crypto Provider.");
        setBuyingCrypto(null);
      }
    } catch (err: any) {
      setErrorMsg("Network error. Please try again.");
      setBuyingCrypto(null);
    }
  };

  const submitSupport = async (e: React.FormEvent) => {
    e.preventDefault();
    setSupportStatus("loading");
    setSupportError("");
    try {
      const res = await fetch("/api/developer/support", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject: supportSubject, message: supportMessage })
      });
      const data = await res.json();
      if (res.ok) {
        setSupportStatus("success");
        setSupportSubject("");
        setSupportMessage("");
        setTimeout(() => setSupportStatus("idle"), 5000);
      } else {
        setSupportStatus("error");
        setSupportError(data.error || "Failed to send message.");
      }
    } catch {
      setSupportStatus("error");
      setSupportError("Network error. Please try again.");
    }
  };

  const sharedTestKey = "wratty_live_sk_test_12345";
  const copyTestKey = () => {
    navigator.clipboard.writeText(sharedTestKey);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const curlMix = `curl -X POST https://wrattygstudio2.zevcloud.app/api/v1/mix \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "mode": "mix",
    "preset": "afrobeats",
    "stems": [
      { "url": "https://your-s3-bucket.com/beat.wav", "role": "beat" },
      { "url": "https://your-s3-bucket.com/vocal.wav", "role": "lead" }
    ]
  }'`;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-300 font-sans selection:bg-green-500/30">
      
      <nav className="sticky top-0 z-50 border-b border-slate-800 bg-[#0a0a0a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-black text-white tracking-tight">WraGstudio <span className="text-green-500">API</span></span>
            <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full font-medium">v1.0</span>
          </div>
          {!isLoaded ? null : isSignedIn ? (
            <span className="text-sm text-slate-400">Logged in as {user?.firstName || "Developer"}</span>
          ) : (
            <SignInButton mode="modal">
              <button className="text-sm font-semibold text-white bg-green-600 hover:bg-green-500 px-4 py-2 rounded-lg transition-colors">Sign In</button>
            </SignInButton>
          )}
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12 space-y-16">
        
        <section>
          <h1 className="text-4xl font-black text-white mb-4 tracking-tight">Developer API</h1>
          <p className="text-lg text-slate-400 leading-relaxed">Integrate a commercial-grade, adaptive mixing engine into your platform. Unlike static AI black-boxes, our deterministic DSP measures the audio (Crest Factor, SNR, PLR) and makes real-time engineering decisions to protect your user's groove and dynamics.</p>
        </section>

        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-32 bg-green-500/5 blur-3xl pointer-events-none"></div>
          <h2 className="text-2xl font-bold text-white mb-6 border-b border-slate-800 pb-4">API Access</h2>

          {!isSignedIn ? (
             <div className="text-center py-12">
                <p className="text-slate-400 mb-6">Please sign in to generate your test key or purchase production access.</p>
                <SignInButton mode="modal">
                  <button className="bg-white text-black font-bold py-3 px-8 rounded-lg hover:bg-slate-200 transition-colors">Sign In to Continue</button>
                </SignInButton>
             </div>
          ) : keys.length > 0 ? (
            <div className="space-y-4">
              <h3 className="text-lg font-bold text-white mb-4">Your Production Keys</h3>
              {keys.map((k) => (
                <div key={k._id} className="p-4 rounded-xl border bg-green-500/10 border-green-500/30">
                  <p className="text-xs uppercase mb-1 text-green-400 font-bold tracking-wider">Live Production Key</p>
                  <code className="text-white font-mono text-lg break-all select-all">{k.apiKey}</code>
                  <p className="text-sm text-slate-400 mt-2">Credits Remaining: <strong className="text-white">{k.credits}</strong></p>
                </div>
              ))}
            </div>
          ) : !profile ? (
            <div>
              <div className="bg-yellow-500/10 border border-yellow-500/20 p-4 rounded-xl mb-8">
                <h3 className="text-yellow-500 font-bold mb-1">Company Verification Required</h3>
                <p className="text-sm text-yellow-200/70">To access the API and purchase production credits, please verify your company details.</p>
              </div>
              <form onSubmit={submitVerification} className="space-y-4 max-w-md">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Company / Platform Name</label>
                  <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} required className="w-full bg-[#0d1117] border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-green-500" placeholder="e.g. WrattyGstudio" />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Company Website URL</label>
                  <input type="text" value={website} onChange={(e) => setWebsite(e.target.value)} required className="w-full bg-[#0d1117] border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-green-500" placeholder="e.g. yourplatform.com" />
                </div>
                {formError && <p className="text-red-400 text-sm">{formError}</p>}
                <button type="submit" disabled={submittingForm} className="w-full bg-white text-black font-bold py-3 px-6 rounded-lg hover:bg-slate-200 disabled:opacity-50">
                  {submittingForm ? "Verifying..." : "Verify Company"}
                </button>
              </form>
            </div>
          ) : (
            <div className="space-y-10">
              <div className="flex items-center gap-2 text-sm text-green-400 bg-green-500/10 w-fit px-3 py-1 rounded-full border border-green-500/20">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                Verified: {profile.companyName}
              </div>

              <div>
                <h3 className="text-lg font-bold text-white mb-3">Your Free Test Key</h3>
                <div className="bg-[#0d1117] border border-slate-700 rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-800">
                    <span className="text-xs text-slate-400 uppercase tracking-widest">Test Key</span>
                    <button onClick={copyTestKey} className="text-xs text-slate-400 hover:text-white">{copiedKey ? "✅ Copied!" : "📋 Copy"}</button>
                  </div>
                  <div className="p-4"><code className="text-yellow-400 font-mono text-sm break-all">{sharedTestKey}</code></div>
                </div>
              </div>

              <div className="border-t border-slate-800"></div>

              <div>
                <h3 className="text-lg font-bold text-white mb-6">Production Packages</h3>
                {errorMsg && <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm text-center font-medium">⚠️ {errorMsg}</div>}

                <div className="grid md:grid-cols-2 gap-6">
                  {/* MIX PACKAGE */}
                  <div className="p-6 rounded-2xl border border-green-500/30 bg-gradient-to-b from-slate-800 to-slate-900 relative shadow-xl flex flex-col justify-between">
                    <div>
                      <div className="absolute top-0 right-6 -translate-y-1/2 bg-green-500 text-white text-xs font-bold px-3 py-1 rounded-full">POPULAR</div>
                      <h4 className="text-lg font-bold text-white mb-2">Full Mix + Master</h4>
                      <p className="text-slate-400 text-sm mb-6">Perfect for platforms sending raw stems.</p>
                      <div className="flex items-baseline gap-1 mb-6"><span className="text-4xl font-black text-white">$2,500</span></div>
                      <ul className="text-sm text-slate-300 space-y-3 mb-8">
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> 1,000 Full Mixes</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Up to 12 tracks per render</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Detailed JSON telemetry report</li>
                      </ul>
                    </div>
                    <div className="space-y-2">
                       {/* PAYSTACK: ONLY FOR NIGERIAN DEVELOPERS */}
                       {region === "NG" && (
                         <button onClick={() => buyCredits("mix")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-green-500 hover:bg-green-400 text-black font-bold py-3 rounded-xl disabled:opacity-50">
                          {buying === "mix" ? "Redirecting..." : "Pay via Paystack (NGN)"}
                        </button>
                       )}
                       {/* CRYPTO: FOR EVERYONE */}
                       <button onClick={() => buyCrypto("mix")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl disabled:opacity-50">
                        {buyingCrypto === "mix" ? "Redirecting..." : "Pay with USDC (Crypto)"}
                      </button>
                      <a href="mailto:wrattyg@gmail.com?subject=Enterprise%20API%20Invoice%20Request%20-%20Mix" className="w-full block text-center bg-transparent border border-slate-600 hover:bg-slate-800 text-white font-bold py-3 rounded-xl transition-colors">
                        Request USD Invoice
                      </a>
                    </div>
                  </div>

                  {/* MASTER PACKAGE */}
                  <div className="p-6 rounded-2xl border border-slate-700 bg-slate-800/50 relative shadow-xl flex flex-col justify-between">
                    <div>
                      <h4 className="text-lg font-bold text-white mb-2">Master Only</h4>
                      <p className="text-slate-400 text-sm mb-6">For platforms with already mixed tracks.</p>
                      <div className="flex items-baseline gap-1 mb-6"><span className="text-4xl font-black text-white">$1,000</span></div>
                      <ul className="text-sm text-slate-300 space-y-3 mb-8">
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> 1,000 Masters</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Adaptive PLR & transient guard</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Detailed JSON telemetry report</li>
                      </ul>
                    </div>
                    <div className="space-y-2">
                      {/* PAYSTACK: ONLY FOR NIGERIAN DEVELOPERS */}
                      {region === "NG" && (
                        <button onClick={() => buyCredits("master")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-slate-600 hover:bg-slate-500 text-white font-bold py-3 rounded-xl disabled:opacity-50">
                          {buying === "master" ? "Redirecting..." : "Pay via Paystack (NGN)"}
                        </button>
                      )}
                      {/* CRYPTO: FOR EVERYONE */}
                      <button onClick={() => buyCrypto("master")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl disabled:opacity-50">
                        {buyingCrypto === "master" ? "Redirecting..." : "Pay with USDC (Crypto)"}
                      </button>
                      <a href="mailto:wrattyg@gmail.com?subject=Enterprise%20API%20Invoice%20Request%20-%20Master" className="w-full block text-center bg-transparent border border-slate-600 hover:bg-slate-800 text-white font-bold py-3 rounded-xl transition-colors">
                        Request USD Invoice
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* SUPPORTED GENRES TABLE */}
        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Supported Genres</h2>
          <p className="mb-4 text-slate-400">
            Pass the <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">preset</code> parameter in your JSON body to change how the Idan mix engine processes the audio.
          </p>
          <div className="overflow-hidden rounded-xl border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-4 font-medium">Preset ID (API Value)</th>
                  <th className="p-4 font-medium">Genre / Style</th>
                  <th className="p-4 font-medium">DSP Profile</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {[
                  { id: "afrobeats", desc: "Afrobeats", detail: "Warm body EQ + 0.95s plate reverb + dynamic beat carving" },
                  { id: "rap", desc: "Hip-Hop / Rap", detail: "Multiband compression + 0.70s room + aggressive slap delay" },
                  { id: "rnb", desc: "R&B", detail: "Silky air boost (+4.0dB) + 1.30s lush plate reverb" },
                  { id: "amapiano", desc: "Electronic / Amapiano", detail: "Heavy sub mono (100Hz) + long 1.20s reverb tails" },
                  { id: "dancehall", desc: "Reggae / Dancehall", detail: "Punchy compression + fast 0.85s tempo-synced delay" },
                  { id: "gospel", desc: "Gospel", detail: "Massive 1.50s cathedral reverb + slow optical compression" },
                  { id: "pop", desc: "Pop", detail: "Maximum air (+5.0dB) + radio-ready 3.5:1 compression" },
                ].map((g) => (
                  <tr key={g.id} className="hover:bg-slate-900/50">
                    <td className="p-4 font-mono text-green-400">{g.id}</td>
                    <td className="p-4 text-slate-300">{g.desc}</td>
                    <td className="p-4 text-slate-500 text-xs">{g.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Make a Request</h2>
          <CodeBlock language="cURL" code={curlMix} />
          <p className="mt-4 text-sm text-slate-400">
            <strong className="text-white">Featured Artist Routing:</strong> If your track has a featured rapper, set their role to <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">"feature"</code>. 
            The engine automatically routes their vocals through the Rap preset (slap delay, heavy saturation) while keeping the main singer on the original genre preset.
          </p>
        </section>

        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Why Adaptive DSP beats Black-Box AI</h2>
          <p className="mb-4 text-slate-400">
            Neural-network mastering tools blindly force an EQ curve onto your audio. Our engine acts like a human engineer: it measures the source and makes logical decisions.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
              <h4 className="font-bold text-white mb-2 text-sm">🎚️ Transient Protection (PLR Guard)</h4>
              <p className="text-xs text-slate-400">If the requested LUFS target will crush the Peak-to-Loudness Ratio below 9.0, the engine refuses to destroy the kick drum's punch. It backs off the loudness to save the groove.</p>
            </div>
            <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
              <h4 className="font-bold text-white mb-2 text-sm">🎛️ Dynamic Beat Carving</h4>
              <p className="text-xs text-slate-400">It doesn't just turn the beat down. It analyzes the vocal's frequency range and applies a dynamic 2dB to 4dB dip in the beat only when the singer is active.</p>
            </div>
            <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
              <h4 className="font-bold text-white mb-2 text-sm">🎤 Smart Noise Gating</h4>
              <p className="text-xs text-slate-400">The denoiser measures artifact distortion (flutter). If a noise reduction level causes robotic artifacts, it automatically backs off the amount of reduction to keep the vocal natural.</p>
            </div>
            <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
              <h4 className="font-bold text-white mb-2 text-sm">🎼 Confidence-Gated Autotune</h4>
              <p className="text-xs text-slate-400">If the pitch tracker isn't confident in a note, the autotune doesn't guess. It holds back the correction to prevent warbling and unnatural glitches.</p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Vocal Tuning API</h2>
          <p className="text-slate-400 mb-4">
            Our pitch correction engine uses a hybrid <strong>Resplice/PSOLA</strong> approach. It automatically detects the song key and preserves formants so the vocal never sounds robotic. 
            You can trigger it via the <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">/api/tune</code> endpoint.
          </p>

          <CodeBlock language="Python" code={`# Internal Adaptive Logic (engine.py)
if q.profile == "poor":
    # Protect bad recordings from robotic artifacts
    s.amount *= 0.70
    s.retune_ms = max(s.retune_ms, 45) 

if singer_err < 10:
    # Singer is already in tune, let them keep their natural vibrato
    s.flex_cents = max(s.flex_cents, 14.0)

if voiced_conf_mean < 0.75:
    # Pitch tracker is unsure (whispers/breath), hold back tuning
    s.conf_gate = (s.conf_gate[0] + 0.06, s.conf_gate[1] + 0.04)`} />

          <div className="overflow-hidden rounded-xl border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-4 font-medium">Feature</th>
                  <th className="p-4 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                <tr className="hover:bg-slate-900/50">
                  <td className="p-4 text-slate-300 font-bold">Engine Type</td>
                  <td className="p-4 text-slate-500 text-xs">Hybrid Resplice + PSOLA (Pitch Synchronous Overlap and Add)</td>
                </tr>
                <tr className="hover:bg-slate-900/50">
                  <td className="p-4 text-slate-300 font-bold">Formant Preservation</td>
                  <td className="p-4 text-slate-500 text-xs">Yes (prevents the "chipmunk" effect during large pitch shifts)</td>
                </tr>
                <tr className="hover:bg-slate-900/50">
                  <td className="p-4 text-slate-300 font-bold">Spectral Restoration</td>
                  <td className="p-4 text-slate-500 text-xs">Restores lost breath and high-frequency air after processing</td>
                </tr>
                <tr className="hover:bg-slate-900/50">
                  <td className="p-4 text-slate-300 font-bold">Key Detection</td>
                  <td className="p-4 text-slate-500 text-xs">Analyzes both the vocal and the beat to snap to the correct scale</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        
        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Under the Hood: The Adaptive DSP Architecture</h2>
          <p className="mb-6 text-slate-400">
            Unlike commercial AI mastering tools that use static, black-box neural networks, WrattyGstudio is a <strong>Deterministic Adaptive Expert System</strong>. It measures the source audio and makes real-time engineering decisions. Here is the complete list of live, active modules running in our engine:
          </p>

          <div className="space-y-8">
            
            {/* 1. Ingestion & Repair */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">1. Ingestion, Alignment & Repair</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>declip.py:</strong> Analyzes waveforms at the sample level. If it detects digital clipping (e.g., flat-topped peaks), it mathematically reconstructs the missing waveform to prevent harsh distortion.</li>
                <li><strong>vocal_align.py:</strong> Uses transient detection to align vocal timing to the beat. It has a confidence gate: if the alignment confidence is too low, it aborts the shift to protect the groove.</li>
                <li><strong>noise_clean.py:</strong> A Wiener-filter based noise gate. It features a "Flutter Guard" that measures artifact distortion. If noise reduction causes robotic fluttering, it automatically backs off the reduction to keep the vocal natural.</li>
              </ul>
            </div>

            {/* 2. Vocal Chain */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">2. The Adaptive Vocal Chain</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>adaptive_tone.py:</strong> Analyzes the vocal against commercial references to apply surgical dynamic EQ cuts (e.g., cutting "mud" at 320Hz and "boxiness" at 600Hz only when needed).</li>
                <li><strong>vocal_polish.py (The Vocal Rider):</strong> Rides the vocal fader dynamically (averaging ~1.48dB of movement) to lock it at the target loudness. It also cleans the gaps between phrases by ducking the noise floor by ~6.9dB.</li>
                <li><strong>adaptive_ambience.py:</strong> Measures the crest factor to set compressor thresholds and makeup gain dynamically.</li>
                <li><strong>vocal_fix.py:</strong> Forwardness Guard. Measures masking at 500Hz-2kHz to prevent the vocal from being pushed so far above the beat that it sounds disconnected.</li>
                <li><strong>polish.py:</strong> Dynamic EQ that tracks harshness (2.5k-4k) and sibilance (5.5k-9k) in real-time.</li>
                <li><strong>opto_comp.py:</strong> Emulates the Teletronix LA-2A optical compressor (EL panel model) for smooth, program-dependent vocal glue.</li>
                <li><strong>vocal_sat.py:</strong> Applies 4x oversampled tube-style saturation based on measured vocal brightness, adding even and odd harmonics without aliasing.</li>
                <li><strong>dsp_tier1.py (ADT):</strong> Generates an Automatic Double Track using a 14ms/22ms delay, LFO modulation, and ±0.30 pan to widen the lead vocal without phase cancellation.</li>
              </ul>
            </div>

            {/* 3. Spatial Engine */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">3. The 3D Spatial Engine (vocal_space.py)</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>The "Tiny Room" (Early Reflections):</strong> Generates ultra-short reflections to simulate the acoustic shadow of the human head. This creates a psychoacoustic 3D effect designed specifically for headphone intimacy, keeping the vocal close to the ear.</li>
                <li><strong>Adaptive Ducking (Sidechain):</strong> The reverb and delay are sidechained to the vocal. While the singer is active, the space is ducked by up to 10.6dB. The moment they stop, the space swells back up.</li>
                <li><strong>Fragment Delay:</strong> A tempo-synced delay that does not echo the whole vocal. It analyzes the syllables, finds the last word of a phrase, and throws only that fragment onto the 1/8 or 1/16 note grid (e.g., 309.3ms).</li>
                <li><strong>Tempo-Synced Reverb:</strong> Generates a stereo plate reverb dynamically, with a low-pass filter that gets darker on every delay repeat to push the echo further into the background.</li>
              </ul>
            </div>

            {/* 4. Beat Interaction */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">4. Beat Interaction & Dynamic Carving</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>Dynamic Beat Carving (vocal_polish.py):</strong> Instead of just turning the beat down, the engine dynamically carves a 2dB to 4dB pocket in the beat's 2kHz-4kHz range only when the vocal is active. The beat literally opens up to surround the vocal.</li>
                <li><strong>beat_punch.py (Kick Transient Punch Preserve):</strong> Measures the kick's crest factor and the beat's low-end share before applying punch. It adds 0-3dB of punch and uses a peak guard to ensure the kick peak never rises more than +0.3dB. If it detects no real kicks or too much noise, it adds nothing.</li>
                <li><strong>song_sections.py:</strong> Analyzes the energy of the beat and vocals to map out Intro/Verse/Chorus. It applies volume automation curves to ride the vocal based on the section's intensity.</li>
              </ul>
            </div>

            {/* 5. Autotune */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">5. Hybrid PSOLA Autotune (vocaltune/)</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>Hybrid Algorithm:</strong> Uses <strong>Resplice</strong> for shifts under 160 cents (ultra-transparent), and <strong>PSOLA</strong> (Pitch Synchronous Overlap and Add) for massive shifts to prevent robotic artifacts.</li>
                <li><strong>Adaptive Blue Notes:</strong> Analyzes the vocal's pitch class. If the artist intentionally bends a note outside the scale and holds it steady, the engine allows it (preserving emotion).</li>
                <li><strong>Confidence Gating:</strong> If the pitch tracker detects whispers or breath (low confidence), it holds back the correction to prevent warbling.</li>
                <li><strong>Spectral Restoration:</strong> Calculates the spectral difference (via Welch's method) between the original and tuned audio, and restores lost breath and high-frequency air via FIR convolution.</li>
              </ul>
            </div>

            {/* 6. Mastering Stages */}
            <div>
              <h3 className="text-lg font-bold text-green-400 mb-2">6. Adaptive Mastering Bus & PLR Guard</h3>
              <ul className="list-disc pl-5 space-y-2 text-sm text-slate-300">
                <li><strong>Adaptive EQ (master_bus.py):</strong> Measures the tonal gaps against commercial references and applies surgical EQ (e.g., cutting sub-bass at 31Hz while boosting the kick at 80Hz).</li>
                <li><strong>mix_balance.py:</strong> Low-Mid Stereo Trims. Applies adaptive Low Shelf (80Hz) and Peak Filter (125Hz) on the Mid channel, while trimming high-frequency Side energy (5.5k-16kHz) to prevent harsh stereo sibilance.</li>
                <li><strong>mix_tone_guard.py:</strong> Dull/Bright Guard. Cuts harsh 6kHz and boosts dull 2kHz using precise FFT band trims against reference profiles.</li>
                <li><strong>Multiband & Glue:</strong> Splits the mix into low, mid, and high bands to apply transparent compression, followed by a gentle glue compressor.</li>
                <li><strong>PLR Guard (Peak-to-Loudness Ratio):</strong> The engine's ultimate safety net. If pushing the loudness to a target like -9 LUFS would crush the transients (dropping the PLR below 9.0), the engine refuses. It backs off the loudness to protect the kick drum's punch and the song's groove.</li>
                <li><strong>True-Peak Clipper:</strong> Before the limiter, the engine catches inter-sample peaks (e.g., 6dB of them) and shaves them off smoothly to prevent distortion.</li>
                <li><strong>Brickwall Limiter & Mono-Bass:</strong> The final limiter hits the target ceiling, while the engine forces everything below 120Hz to mono, ensuring the bass and kick are dead center and punchy.</li>
                <li><strong>Stereo Correlation Guard:</strong> Monitors the phase of the final mix. If the mix is out of phase, it collapses the sides to protect mono compatibility.</li>
              </ul>
            </div>

          </div>
        </section>


        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-2xl font-bold text-white mb-2">Developer Support</h2>
          <div className="grid md:grid-cols-2 gap-8 mt-6">
            <div>
              <h3 className="text-lg font-bold text-white mb-4">Send an Email</h3>
              {supportStatus === "success" ? (
                <div className="p-6 bg-green-500/10 border border-green-500/30 rounded-xl text-center">
                  <h3 className="text-green-400 font-bold mb-2">Message Sent!</h3>
                  <p className="text-sm text-green-200/70">Our team will reply shortly.</p>
                </div>
              ) : (
                <form onSubmit={submitSupport} className="space-y-4">
                  <input type="text" value={supportSubject} onChange={(e) => setSupportSubject(e.target.value)} required className="w-full bg-[#0d1117] border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-green-500" placeholder="Subject (e.g. Integration issue)" />
                  <textarea value={supportMessage} onChange={(e) => setSupportMessage(e.target.value)} required rows={4} className="w-full bg-[#0d1117] border border-slate-700 rounded-lg p-3 text-white focus:outline-none focus:border-green-500 resize-none" placeholder="Describe your issue..."></textarea>
                  {supportStatus === "error" && <p className="text-red-400 text-sm">{supportError}</p>}
                  <button type="submit" disabled={supportStatus === "loading"} className="w-full bg-white hover:bg-slate-200 text-black font-bold py-3 rounded-lg disabled:opacity-50">
                    {supportStatus === "loading" ? "Sending..." : "Submit Ticket"}
                  </button>
                </form>
              )}
            </div>
            <div className="flex flex-col">
              <h3 className="text-lg font-bold text-white mb-4">Instant Messaging</h3>
              <div className="flex-1 flex flex-col justify-center bg-slate-800/50 rounded-xl p-6 border border-slate-700 text-center">
                <p className="text-slate-400 text-sm mb-6">Prefer to chat directly with an engineer? Reach out on WhatsApp.</p>
                <a href="https://wa.me/2347074216877?text=Hi,%20I%20need%20support%20with%20the%20WraGstudio%20API" target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center gap-2 bg-green-600 hover:bg-green-500 text-white font-bold py-3 px-6 rounded-lg transition-colors">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                  Chat on WhatsApp
                </a>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
