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
      if (data.url) alert("Redirecting to: " + data.url); // window.location.href = data.url;
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
      if (data.url) alert("Redirecting to: " + data.url); // window.location.href = data.url;
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
          <p className="text-lg text-slate-400 leading-relaxed">Automate commercial-grade mixing and mastering with the Idan mix Engine.</p>
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
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Stem alignment & cleanup</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Commercial Master</li>
                      </ul>
                    </div>
                    <div className="space-y-2">
                       <button onClick={() => buyCredits("mix")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-green-500 hover:bg-green-400 text-black font-bold py-3 rounded-xl disabled:opacity-50">
                        {buying === "mix" ? "Redirecting..." : "Pay via Paystack (NGN)"}
                      </button>
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
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Loudness & tone matching</li>
                        <li className="flex items-center gap-2"><span className="text-green-500">✓</span> Commercial Master</li>
                      </ul>
                    </div>
                    <div className="space-y-2">
                      <button onClick={() => buyCredits("master")} disabled={buying !== null || buyingCrypto !== null} className="w-full bg-slate-600 hover:bg-slate-500 text-white font-bold py-3 rounded-xl disabled:opacity-50">
                        {buying === "master" ? "Redirecting..." : "Pay via Paystack (NGN)"}
                      </button>
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

        <section>
          <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Make a Request</h2>
          <CodeBlock language="cURL" code={curlMix} />
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
