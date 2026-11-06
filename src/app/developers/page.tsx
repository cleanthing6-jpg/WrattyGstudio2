"use client";

import { useState } from "react";

const CodeBlock = ({ code, language }: { code: string; language: string }) => {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative mt-4 rounded-xl overflow-hidden bg-[#0d1117] border border-slate-800 shadow-2xl">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161b22] border-b border-slate-800">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">{language}</span>
        <button
          onClick={copyToClipboard}
          className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1"
        >
          {copied ? "✅ Copied!" : "📋 Copy"}
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        <pre className="text-sm text-[#c9d1d9] font-mono leading-relaxed">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
};

export default function DeveloperDocs() {
  const curlMix = `curl -X POST https://wrattygstudio2.zevcloud.app/api/v1/mix \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "stems": [
      { "url": "https://your-s3-bucket.com/beat.wav", "role": "beat" },
      { "url": "https://your-s3-bucket.com/vocal.wav", "role": "lead" }
    ],
    "preset": "afrobeats",
    "loudness": "HIGH"
  }'`;

  const resMix = `{
  "success": true,
  "jobId": "e8be217991d24ad1bc333d9a022140c9",
  "message": "Mix started successfully. Poll the status endpoint."
}`;

  const curlStatus = `curl -X GET "https://wrattygstudio2.zevcloud.app/api/v1/status?id=YOUR_JOB_ID" \\
  -H "Authorization: Bearer YOUR_API_KEY"`;

  const resStatus = `{
  "status": "done",
  "url": "https://wrattyg--wratty-files-web.modal.run/f/fx/mix-high.flac",
  "files": {
    "mp3": "https://.../mix-high.mp3",
    "flac": "https://.../mix-high.flac"
  },
  "lufs": -10.27,
  "true_peak_dbfs": -1.12
}`;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-300 font-sans selection:bg-green-500/30">
      
      {/* Navbar */}
      <nav className="sticky top-0 z-50 border-b border-slate-800 bg-[#0a0a0a]/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-black text-white tracking-tight">
              WraGstudio <span className="text-green-500">API</span>
            </span>
            <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-full font-medium">v1.0</span>
          </div>
          <a href="/pricing" className="text-sm font-semibold text-white bg-green-600 hover:bg-green-500 px-4 py-2 rounded-lg transition-colors">
            Get API Keys
          </a>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-12 flex flex-col md:flex-row gap-12">
        
        {/* Sidebar Navigation (Desktop) */}
        <aside className="hidden md:block w-64 shrink-0">
          <div className="sticky top-24 space-y-6">
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Getting Started</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#intro" className="text-green-400 font-medium">Introduction</a></li>
                <li><a href="#auth" className="hover:text-white transition-colors">Authentication</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Endpoints</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#mix" className="hover:text-white transition-colors flex items-center gap-2"><span className="text-xs bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded font-mono">POST</span> /mix</a></li>
                <li><a href="#status" className="hover:text-white transition-colors flex items-center gap-2"><span className="text-xs bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded font-mono">GET</span> /status</a></li>
              </ul>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 max-w-3xl space-y-16">
          
          {/* Intro */}
          <section id="intro">
            <h1 className="text-4xl font-bold text-white mb-4 tracking-tight">WraGstudio Developer API</h1>
            <p className="text-lg text-slate-400 leading-relaxed">
              Integrate the power of the <strong className="text-white">Idan mix Engine</strong> directly into your platform. 
              Automate commercial-grade mixing and mastering for your users with a single API call.
            </p>
          </section>

          {/* Authentication */}
          <section id="auth" className="scroll-mt-24">
            <h2 className="text-2xl font-bold text-white mb-4 border-b border-slate-800 pb-2">Authentication</h2>
            <p className="mb-4 text-slate-400">
              The WraGstudio API uses Bearer tokens to authenticate requests. You must include your API key in the <code className="text-green-400 bg-slate-900 px-1.5 py-0.5 rounded">Authorization</code> header.
            </p>
            <div className="bg-yellow-500/10 border border-yellow-500/20 p-4 rounded-xl text-yellow-200/80 text-sm mb-4">
              <strong>⚠️ Security Warning:</strong> Never expose your API key in client-side code (browsers, mobile apps). Always make requests from your secure backend server.
            </div>
            <CodeBlock language="HTTP Header" code={`Authorization: Bearer wratty_live_sk_your_secret_key`} />
          </section>

          {/* Mix Endpoint */}
          <section id="mix" className="scroll-mt-24">
            <div className="flex items-center gap-3 mb-4 border-b border-slate-800 pb-2">
              <span className="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded font-mono font-bold">POST</span>
              <h2 className="text-2xl font-bold text-white font-mono">/api/v1/mix</h2>
            </div>
            <p className="mb-4 text-slate-400">
              Submits a new job to the Idan mix engine. You provide the URLs of the stems, and the engine handles the rest.
            </p>
            
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-2 mt-6">Request Body</h3>
            <ul className="space-y-3 text-sm mb-6">
              <li><strong className="text-white font-mono">stems</strong> <span className="text-slate-500">(Array, required)</span> - Array of objects containing the URL and role of each track.</li>
              <li><strong className="text-white font-mono">preset</strong> <span className="text-slate-500">(String, optional)</span> - Genre preset. Default is "afrobeats".</li>
              <li><strong className="text-white font-mono">loudness</strong> <span className="text-slate-500">(String, optional)</span> - Target loudness. Options: LOW, MEDIUM, HIGH.</li>
            </ul>

            <CodeBlock language="cURL" code={curlMix} />
            
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-2 mt-8">Response</h3>
            <CodeBlock language="JSON" code={resMix} />
          </section>

          {/* Status Endpoint */}
          <section id="status" className="scroll-mt-24">
            <div className="flex items-center gap-3 mb-4 border-b border-slate-800 pb-2">
              <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded font-mono font-bold">GET</span>
              <h2 className="text-2xl font-bold text-white font-mono">/api/v1/status</h2>
            </div>
            <p className="mb-4 text-slate-400">
              Checks the status of an ongoing mix job. Because rendering takes time, you should poll this endpoint every 5 seconds until the status is <code className="text-white bg-slate-800 px-1.5 rounded">done</code>.
            </p>
            
            <CodeBlock language="cURL" code={curlStatus} />
            
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-2 mt-8">Response</h3>
            <CodeBlock language="JSON" code={resStatus} />
          </section>

          {/* CTA */}
          <div className="bg-gradient-to-br from-slate-900 to-slate-800 border border-slate-700 p-8 rounded-2xl text-center mt-12">
            <h3 className="text-2xl font-bold text-white mb-2">Ready to scale your platform?</h3>
            <p className="text-slate-400 mb-6">Get production API keys and start mixing tracks for your users today.</p>
            <a href="/pricing" className="inline-block bg-white text-black font-bold px-8 py-3 rounded-lg hover:bg-slate-200 transition-colors">
              Purchase API Credits
            </a>
          </div>

        </main>
      </div>
    </div>
  );
}
