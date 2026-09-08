"use client";
import { useEffect, useState } from "react";

type Mix = { id: string; name: string; url: string; createdAt?: string };

export default function MixesList() {
  const [mixes, setMixes] = useState<Mix[] | null>(null);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const res = await fetch("/api/mixes");
      if (!res.ok) throw new Error("failed");
      const d = await res.json();
      setMixes(d.mixes || []);
    } catch {
      setErr("Could not load your mixes");
      setMixes([]);
    }
  };

  useEffect(() => { load(); }, []);

  const remove = async (id: string) => {
    await fetch("/api/mixes?id=" + encodeURIComponent(id), { method: "DELETE" });
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-bold">My Mixes</h3>
        <button onClick={load} className="text-xs text-gray-400 hover:text-gray-600">↻ Refresh</button>
      </div>
      {err && <p className="text-red-500 text-sm mb-2">{err}</p>}
      {mixes === null ? (
        <p className="text-gray-400 text-sm">Loading…</p>
      ) : mixes.length === 0 ? (
        <p className="text-gray-400 text-sm">No mixes yet — bake one in the Studio and it appears here.</p>
      ) : (
        <div className="space-y-2">
          {mixes.map((m) => (
            <div key={m.id} className="bg-green-50 border border-green-500/40 rounded-xl p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-green-800 text-sm truncate">{m.name}</div>
                <button onClick={() => remove(m.id)} className="text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
              </div>
              <audio controls src={m.url} className="w-full mt-2" preload="none" />
              <a href={m.url} download={m.name + ".wav"} className="inline-block mt-2 text-xs bg-green-500 hover:bg-green-400 text-black font-bold px-3 py-1.5 rounded-lg">
                ⬇ Download
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
