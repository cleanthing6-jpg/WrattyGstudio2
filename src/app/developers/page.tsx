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

  const activeKey = keys[0]?.apiKey || "YOUR_API_KEY";

  const curlMix = `curl -X POST https://wrattygstudio2.zevcloud.app/api/v1/mix \\
  -H "Authorization: Bearer ${activeKey}" \\
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

          {/* DYNAMIC API KEY SECTION */}
          <section className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
            <h2 className="text-2xl font-bold text-white mb-6">Your API Keys</h2>
            
            {!isSignedIn ? (
              <p className="text-slate-400">Please sign in to generate your free test key.</p>
            ) : keys.length > 0 ? (
              <div className="space-y-4">
                {keys.map((k) => (
                  <div key={k._id} className={`p-4 rounded-xl border ${k.isTest ? 'bg-yellow-500/10 border-yellow-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
                    <p className={`text-xs uppercase mb-1 ${k.isTest ? 'text-yellow-400' : 'text-green-400'}`}>
                      {k.isTest ? "Free Test Key (5 Mixes)" : "Live Production Key"}
                    </p>
                    <code className="text-white font-mono text-lg break-all">{k.apiKey}</code>
                    <p className="text-sm text-slate-400 mt-2">Credits Remaining: <strong className="text-white">{k.credits}</strong></p>
                    
                    {k.isTest && (
                      <button onClick={buyCredits} disabled={buying} className="mt-4 bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-6 rounded-lg text-sm transition-colors">
                        {buying ? "Redirecting..." : "Upgrade to 1,000 Mixes ($2,500)"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400">Generating your free test key...</p>
            )}
          </section>

          {/* GENRE SELECTION SECTION */}
          <section>
            <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Supported Genres (Presets)</h2>
            <p className="mb-4 text-slate-400">
              Pass the <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">preset</code> parameter in your JSON body to change how the Idan mix engine processes the audio.
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
