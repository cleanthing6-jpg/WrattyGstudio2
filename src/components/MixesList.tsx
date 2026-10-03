"use client";

import { useEffect, useState } from "react";

type Mix = {
  id: string;
  name: string;
  url: string;
  mp3?: string;
  flac?: string;
  createdAt?: string;
};

export function MixesList() {
  const [mixes, setMixes] = useState<Mix[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");

  async function load() {
    setLoading(true); setErr(""); setNote("");
    try {
      const res = await fetch("/api/mixes");
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d?.error || "Could not load your mixes");
      setMixes(Array.isArray(d?.mixes) ? d.mixes : []);
      const bits: string[] = [];
      if (d?.renderError) bits.push("renders: " + d.renderError);
      if (d?.mongoError) bits.push("legacy: " + d.mongoError);
      if (bits.length) setNote("Part of your library did not load (" + bits.join("; ") + ")");
    } catch (e: any) {
      setErr((e && e.message) || "Could not load your mixes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function remove(id: string) {
    if (!confirm("Delete this mix?")) return;
    await fetch("/api/mixes?id=" + encodeURIComponent(id), { method: "DELETE" });
    setMixes((m) => m.filter((x) => x.id !== id));
  }

  function srcFor(m: Mix, fmt: "mp3" | "flac") {
    if (m.id.startsWith("job:")) return "/api/download?id=" + encodeURIComponent(m.id) + "&format=" + fmt;
    return fmt === "flac" ? (m.flac || "") : (m.mp3 || m.url);
  }
  function hrefFor(m: Mix, fmt: "mp3" | "flac") {
    if (m.id.startsWith("job:")) return "/api/download?id=" + encodeURIComponent(m.id) + "&format=" + fmt + "&dl=1";
    return fmt === "flac" ? (m.flac || "") : (m.mp3 || m.url);
  }

  return (
    <div className="space-y-4">
      {err && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">
          {err}
          <button onClick={load} className="ml-2 underline">retry</button>
        </div>
      )}
      {note && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          {note}
        </div>
      )}
      {loading && <p className="text-sm text-gray-500">Loading your mixes…</p>}
      {!loading && !err && mixes.length === 0 && (
        <p className="text-sm text-gray-500">No mixes yet — your finished renders appear here.</p>
      )}

      {mixes.map((m) => {
        const hasFlac = m.id.startsWith("job:") ? true : !!m.flac;
        const hasMp3 = !!(m.mp3 || m.url);
        return (
          <div key={m.id} className="rounded-xl border border-gray-200 p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-900">{m.name}</p>
                {m.createdAt && (
                  <p className="text-xs text-gray-500">{new Date(m.createdAt).toLocaleString()}</p>
                )}
              </div>
              <button
                onClick={() => remove(m.id)}
                className="shrink-0 text-xs font-semibold text-red-600 hover:underline"
              >
                Delete
              </button>
            </div>

            {hasMp3 && (
              <audio controls src={srcFor(m, "mp3")} className="w-full mt-2" preload="none" />
            )}

            <div className="flex flex-wrap gap-2 mt-2">
              {hasMp3 && (
                <a
                  href={hrefFor(m, "mp3")}
                  download={m.name + ".mp3"}
                  className="text-xs bg-green-500 hover:bg-green-400 text-black font-bold px-3 py-1.5 rounded-lg"
                >
                  ⬇ MP3
                </a>
              )}
              {hasFlac && (
                <a
                  href={hrefFor(m, "flac")}
                  download={m.name + ".flac"}
                  className="text-xs bg-slate-800 hover:bg-slate-700 text-white font-bold px-3 py-1.5 rounded-lg"
                >
                  ⬇ FLAC lossless
                </a>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default MixesList;
