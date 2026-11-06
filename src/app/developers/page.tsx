"use client";

import { useState, useEffect } from "react";
import { useUser, SignInButton } from "@clerk/nextjs";

const CodeBlock = ({ code, language }: { code: string; language: string }) => {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative mt-4 rounded-xl overflow-hidden bg-[#0d1117] border border-slate-800">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-800">
        <span className="text-xs font-semibold text-slate-400 uppercase">{language}</span>
        <button onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000); }} className="text-xs text-slate-400 hover:text-white">
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
  const [buying, setBuying] = useState(false);

  useEffect(() => {
    if (isSignedIn) {
      fetch("/api/developer/keys")
        .then((res) => res.json())
        .then((data) => setKeys(data.keys));
    }
  }, [isSignedIn]);

  const buyCredits = async () => {
    setBuying(true);
    const res = await fetch("/api/developer/buy", { method: "POST" });
    const data = await res.json();
    if (data.url) window.location.href = data.url;
    else setBuying(false);
  };

  // The code examples use the shared test key so anyone can copy/paste
  const sharedTestKey = "wratty_live_sk_test_12345";

  const curlMix = `curl -X POST https://wrattygstudio2.zevcloud.app/api/v1/mix \\
  -H "Authorization: Bearer ${sharedTestKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "mode": "mix",
    "preset": "afrobeats",
    "loudness": "HIGH",
    "stems": [
      { "url": "https://your-s3-bucket.com/beat.wav", "role": "beat" },
      { "url": "https://your-s3-bucket.com/vocal.wav", "role": "lead" }
    ]
  }'`;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-300 font-sans">
      <nav className="sticky top-0 z-50 border-b border-slate-800 bg-[#0a0a0a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-black text-white">WraGstudio <span className="text-green-500">API</span></span>
          {!isLoaded ? null : isSignedIn ? (
            <span className="text-sm text-slate-400">Logged in as {user?.firstName || "Developer"}</span>
          ) : (
            <SignInButton mode="modal">
              <button className="text-sm font-semibold text-white bg-green-600 hover:bg-green-500 px-4 py-2 rounded-lg">Sign In</button>
            </SignInButton>
          )}
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-12 flex flex-col md:flex-row gap-12">
        <main className="flex-1 max-w-3xl space-y-16">
          
          <section>
            <h1 className="text-4xl font-bold text-white mb-4">Developer API</h1>
            <p className="text-lg text-slate-400">Automate commercial-grade mixing and mastering with the Idan mix Engine.</p>
          </section>

          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
            <h2 className="text-2xl font-bold text-white mb-2">API Access</h2>
            
            <div className="mt-4 mb-8">
              <p className="text-sm text-slate-400 mb-2">Public Test Key (Shared, 5 credits max):</p>
              <div className="bg-yellow-500/10 border border-yellow-500/30 p-4 rounded-xl flex justify-between items-center">
                <code className="text-yellow-400 font-mono text-lg select-all">{sharedTestKey}</code>
              </div>
            </div>

            {!isSignedIn ? (
              <p className="text-slate-400 text-sm border-t border-slate-800 pt-6">Sign in to purchase production API keys.</p>
            ) : keys.length > 0 ? (
              <div className="space-y-4 border-t border-slate-800 pt-6">
                <h3 className="text-lg font-bold text-white mb-4">Your Production Keys</h3>
                {keys.map((k) => (
                  <div key={k._id} className="p-4 rounded-xl border bg-green-500/10 border-green-500/30">
                    <p className="text-xs uppercase mb-1 text-green-400">Live Production Key</p>
                    <code className="text-white font-mono text-lg break-all select-all">{k.apiKey}</code>
                    <p className="text-sm text-slate-400 mt-2">Credits Remaining: <strong className="text-white">{k.credits}</strong></p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 bg-slate-800/50 rounded-xl border border-slate-700 border-dashed mt-6">
                <p className="text-slate-400 mb-4 text-sm">Need a dedicated production key that doesn't run out?</p>
                <button onClick={buyCredits} disabled={buying} className="bg-green-500 hover:bg-green-600 text-white font-bold py-3 px-8 rounded-lg">
                  {buying ? "Redirecting to Paystack..." : "Buy 1,000 Mixes ($2,500)"}
                </button>
              </div>
            )}
          </section>

          <section>
            <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Supported Genres (Presets)</h2>
            <p className="mb-4 text-slate-400">
              Pass the <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">preset</code> parameter in your JSON body to choose a genre.
            </p>
            <div className="overflow-hidden rounded-xl border border-slate-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th className="p-4 font-medium">Preset Value</th>
                    <th className="p-4 font-medium">Genre / Style</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {[
                    { id: "afrobeats", desc: "Afrobeats (Recommended)" },
                    { id: "afrobeats_street", desc: "Afrobeats Street (Lamba)" },
                    { id: "rap", desc: "Hip-Hop / Rap" },
                    { id: "rnb", desc: "R&B" },
                    { id: "dancehall", desc: "Reggae / Dancehall" },
                    { id: "pop", desc: "Pop" },
                    { id: "amapiano", desc: "Electronic / Amapiano" },
                    { id: "gospel", desc: "Gospel" },
                  ].map((g) => (
                    <tr key={g.id} className="hover:bg-slate-900/50">
                      <td className="p-4 font-mono text-green-400">{g.id}</td>
                      <td className="p-4 text-slate-300">{g.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Make a Request</h2>
            <CodeBlock language="cURL" code={curlMix} />
          </section>

        </main>
      </div>
    </div>
  );
}
