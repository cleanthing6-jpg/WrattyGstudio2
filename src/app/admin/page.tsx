"use client";

import { useState, useEffect } from "react";

export default function AdminDashboard() {
  const [clients, setClients] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [credits, setCredits] = useState("1000");
  const [loading, setLoading] = useState(false);
  const [newKey, setNewKey] = useState("");

  const fetchClients = async () => {
    const res = await fetch("/api/admin/keys");
    if (res.ok) {
      const data = await res.json();
      setClients(data.clients);
    }
  };

  useEffect(() => {
    fetchClients();
  }, []);

  const generateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setNewKey("");
    
    const res = await fetch("/api/admin/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, credits }),
    });

    if (res.ok) {
      const data = await res.json();
      setNewKey(data.apiKey);
      setName("");
      fetchClients(); // Refresh the list
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Developer API Dashboard</h1>

        {/* Create New Key Form */}
        <div className="bg-slate-800 p-6 rounded-xl mb-8 border border-slate-700">
          <h2 className="text-xl font-semibold mb-4">Generate New API Key</h2>
          <form onSubmit={generateKey} className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="block text-sm text-slate-400 mb-1">Client Name</label>
              <input 
                type="text" 
                value={name} 
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. BeatStars"
                className="w-full bg-slate-900 border border-slate-600 rounded-lg p-3 text-white"
                required
              />
            </div>
            <div className="w-48">
              <label className="block text-sm text-slate-400 mb-1">Credits</label>
              <input 
                type="number" 
                value={credits} 
                onChange={(e) => setCredits(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg p-3 text-white"
                required
              />
            </div>
            <button 
              type="submit" 
              disabled={loading}
              className="bg-green-500 hover:bg-green-600 text-white font-bold py-3 px-6 rounded-lg transition"
            >
              {loading ? "Generating..." : "Generate Key"}
            </button>
          </form>

          {newKey && (
            <div className="mt-4 p-4 bg-green-500/20 border border-green-500 rounded-lg">
              <p className="text-green-400 font-semibold mb-1">Key Generated Successfully!</p>
              <code className="text-white bg-black p-2 rounded block font-mono">{newKey}</code>
              <p className="text-sm text-slate-400 mt-2">Copy this and send it to the client. They will put it in their `.env` file.</p>
            </div>
          )}
        </div>

        {/* Existing Clients List */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-slate-900 text-slate-400 text-sm">
              <tr>
                <th className="p-4">Client</th>
                <th className="p-4">API Key</th>
                <th className="p-4">Credits Remaining</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client._id} className="border-t border-slate-700">
                  <td className="p-4 font-semibold">{client.name}</td>
                  <td className="p-4 font-mono text-sm text-green-400">{client.apiKey}</td>
                  <td className="p-4">{client.credits}</td>
                </tr>
              ))}
              {clients.length === 0 && (
                <tr>
                  <td colSpan={3} className="p-8 text-center text-slate-500">No clients yet. Generate a key above.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
