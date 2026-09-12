"use client";
import { useUser } from "@clerk/nextjs";

import {useState, useRef } from "react";
import { useUploadThing } from "@/utils/uploadthing";
import { masterStage } from "@/lib/masterStage";

type Stem = { url: string; name: string; role: string };

const STYLES = [
  { value: "AFROBEAT", label: "Afrobeats — recommended" },
  { value: "HIPHOP_GRIME", label: "Afrobeats / Urban — recommended" },
  { value: "REGGAE_DUB", label: "Reggae / Dancehall" },
  { value: "POP", label: "Pop" },
  { value: "ELECTRONIC", label: "Electronic / Amapiano" },
  { value: "ACOUSTIC", label: "Acoustic" },
  { value: "ROCK_INDIE", label: "Rock / Indie" },
  { value: "OTHER", label: "Other" },
];

const RATE = 44100;
const MAX_WAV_BYTES = 128 * 1024 * 1024;
const isVoice = (s: string) => /lead|vocal|back|ad|harmon|main/i.test(s || "");
const isRoexReady = (u: string) => /\.(wav|mp3|flac|aiff?)(\?|#|$)/i.test(u);
const isBeat = (s: Stem) => /beat|instru/i.test(s.role + " " + s.name);

function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(
      () => reject(new Error(label + " took longer than " + Math.round(ms / 1000) + "s — check your connection and try again.")),
      ms
    );
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

async function fetchWithTimeout(url: string, ms: number): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(t);
  }
}

function encodeWav(buf: AudioBuffer): Blob {
  const ch = buf.numberOfChannels;
  const len = buf.length;
  const blockAlign = ch * 2;
  const dataSize = len * blockAlign;
  const ab = new ArrayBuffer(44 + dataSize);
  const v = new DataView(ab);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + dataSize, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, ch, true); v.setUint32(24, buf.sampleRate, true);
  v.setUint32(28, buf.sampleRate * blockAlign, true); v.setUint16(32, blockAlign, true);
  v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, dataSize, true);
  const data: Float32Array[] = [];
  for (let c = 0; c < ch; c++) data.push(buf.getChannelData(c));
  let off = 44;
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < ch; c++) {
      let s = data[c][i];
      if (s > 1) s = 1; else if (s < -1) s = -1;
      v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
  }
  return new Blob([ab], { type: "audio/wav" });
}

async function convertToWavFile(st: Stem): Promise<File> {
  const res = await fetchWithTimeout(st.url, 90000);
  const ab = await res.arrayBuffer();

  const AC: any = (window as any).AudioContext || (window as any).webkitAudioContext;
  const tmp = new AC();
  let decoded: AudioBuffer;
  try {
    decoded = await withTimeout(tmp.decodeAudioData(ab), 90000, "Decoding " + st.name);
  } finally {
    try { tmp.close(); } catch {}
  }

  const voice = isVoice(st.role) || isVoice(st.name);
  const dur = decoded.duration || 0;
  let channels = voice ? 1 : Math.min(2, decoded.numberOfChannels);
  if (dur * RATE * channels * 2 > MAX_WAV_BYTES) channels = 1;
  let rate = RATE;
  if (dur * rate * channels * 2 > MAX_WAV_BYTES) rate = 32000;
  if (dur * rate * channels * 2 > MAX_WAV_BYTES) rate = 24000;

  const off = new OfflineAudioContext(channels, Math.max(1, Math.ceil(dur * rate)), rate);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start(0);
  const rendered = await off.startRendering();

  const name = (st.name || "stem").replace(/\.[^.]+$/, "") + ".wav";
  return new File([encodeWav(rendered)], name, { type: "audio/wav" });
}

export default function AiMixer({ stems }: { stems: Stem[] }) {
  const uploadErrorRef = useRef("");
  const [uploadedUrls, setUploadedUrls] = useState<Record<string, string>>({});
  const { startUpload } = useUploadThing("audioUploader", {
    onUploadError: (e) => {
      const msg = (e as any)?.message || String(e);
      uploadErrorRef.current = msg;
      console.error("[UploadThing]", e);
      setErr("UploadThing: " + msg);
    },
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [style, setStyle] = useState("AFROBEAT");
  const [lufs, setLufs] = useState(-8);
  const [roexLoudness, setRoexLoudness] = useState("MEDIUM");
  const [beatLockMode, setBeatLockMode] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [prepared, setPrepared] = useState<Stem[]>([]);
  const [previewUrl, setPreviewUrl] = useState("");
  const [finalUrl, setFinalUrl] = useState("");
  const { user } = useUser();
  const isOwner = String(user?.id || "") === "user_3IqTsednC0Bqdk3JMxeGzW6zdGD";

  const list = Array.isArray(stems) ? stems : [];
  const ready = list.length >= 2;

  async function generate() {
    if (!ready || busy) return;
    setBusy(true); setErr(""); setMsg(""); setPreviewUrl(""); setFinalUrl(""); setTaskId("");
    try {
      const done: Stem[] = [];
      for (let i = 0; i < list.length; i++) {
        const st = list[i];
        if (isRoexReady(st.name)) { done.push(st); continue; }
        const cacheKey = (st.role || "") + ":" + (st.url || st.name);
        const cachedUrl = uploadedUrls[cacheKey];
        if (cachedUrl) {
          setMsg("Reusing already-uploaded " + (st.role || st.name));
          done.push({ url: cachedUrl, name: st.name, role: st.role });
          continue;
        }

        setMsg("Converting stem " + (i + 1) + " of " + list.length + " — " + (st.role || st.name) + "…");
        const file = await withTimeout(convertToWavFile(st), 150000, "Converting " + st.name);

        setMsg("Uploading stem " + (i + 1) + " of " + list.length + " (" + Math.round(file.size / 1048576) + "MB) — " + (st.role || st.name) + "…");
        let url = "";
        let why = "";
        for (let attempt = 1; attempt <= 2 && !url; attempt++) {
          try {
            uploadErrorRef.current = "";
            const up = await withTimeout(startUpload([file]), 240000, "Uploading " + st.name);
            const item: any = up && up[0];
            url =
              (item && (item.ufsUrl || item.url)) ||
              (item && item.serverData && (item.serverData.ufsUrl || item.serverData.url)) ||
              "";
            if (!url) why = uploadErrorRef.current || "no file result returned";
          } catch (e: any) {
            why = (e && e.message) || String(e);
          }
          if (!url && attempt === 1) {
            setMsg("Retrying upload for " + (st.role || st.name) + "...");
            await new Promise((r) => setTimeout(r, 1500));
          }
        }
        if (!url) {
          throw new Error(
            "Upload failed for " + st.name + " (" + Math.round(file.size / 1048576) + "MB): " + (why || "unknown")
          );
        }
        setUploadedUrls((prev) => ({ ...prev, [(st.role || "") + ":" + (st.url || st.name)]: url }));
        done.push({ url, name: st.name, role: st.role });
      }

      setPrepared(done);
      const beatStem = done.find(isBeat);
      if (beatLockMode && beatStem) {
        setTaskId("");
        const vocals = done.filter((st) => !isBeat(st));
        if (!vocals.length) throw new Error("Beat-Lock needs at least one vocal stem");
        setMsg("Beat-Lock: sending " + vocals.length + " vocal stem(s) to RoEx...");
        const vpost = await withTimeout(fetch("/api/roex-mix", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stems: vocals, style }) }), 120000, "RoEx vocal request");
        const vdata = await vpost.json().catch(() => ({}));
        if (!vpost.ok || !vdata.taskId) throw new Error(vdata.error || "RoEx could not start the vocal mix (code " + vpost.status + ")");
        let roexVocalUrl = "";
        for (let k = 0; k < 30 && !roexVocalUrl; k++) {
          setMsg("RoEx is mixing your vocals - attempt " + (k + 1) + " of 30");
          await new Promise((r) => setTimeout(r, 5000));
          const vs = await fetchWithTimeout("/api/roex-mix?taskId=" + encodeURIComponent(vdata.taskId), 60000);
          const vsd = await vs.json().catch(() => ({}));
          if (vsd.error) throw new Error(vsd.error);
          if (vsd.status === "preview" && vsd.url) roexVocalUrl = vsd.url;
        }
        if (!roexVocalUrl) throw new Error("RoEx vocal mix timed out - try again in a minute");
        setTaskId("");
        setMsg("Beat protected - RoEx vocals ready, combining...");
        const AC: any = (window as any).AudioContext || (window as any).webkitAudioContext;
        const ctx: any = new AC();
        const loadAudio = async (url: string, label: string): Promise<AudioBuffer> => {
          const res = await fetchWithTimeout(url, 180000);
          if (!res.ok) throw new Error(label + " fetch failed (" + res.status + ")");
          return await withTimeout(ctx.decodeAudioData(await res.arrayBuffer()), 120000, label + " decode");
        };
        const [beatBuf, vocalBuf] = await Promise.all([loadAudio(beatStem.url, "Beat"), loadAudio(roexVocalUrl, "RoEx vocal mix")]);
        const sampleRate = ctx.sampleRate;
        const beatLen = Math.max(1, beatBuf.length);
        const off = new OfflineAudioContext(2, beatLen, sampleRate);
        const beatCopy = off.createBuffer(2, beatLen, sampleRate);
        const vocalCopy = off.createBuffer(2, beatLen, sampleRate);
        for (let c = 0; c < 2; c++) {
          const beatSrc = beatBuf.getChannelData(Math.min(c, beatBuf.numberOfChannels - 1));
          const beatDst = beatCopy.getChannelData(c);
          for (let i = 0; i < beatLen; i++) beatDst[i] = beatSrc[i] || 0;
          const vocalSrc = vocalBuf.getChannelData(Math.min(c, vocalBuf.numberOfChannels - 1));
          const vocalDst = vocalCopy.getChannelData(c);
          const vLen = Math.min(vocalSrc.length, beatLen);
          for (let i = 0; i < vLen; i++) vocalDst[i] = vocalSrc[i] || 0;
        }
        const beatNode = off.createBufferSource();
        beatNode.buffer = beatCopy;
        const vocalNode = off.createBufferSource();
        vocalNode.buffer = vocalCopy;
        const vg = off.createGain();
        vg.gain.value = 1.2;
        beatNode.connect(off.destination);
        vocalNode.connect(vg).connect(off.destination);
        beatNode.start(0);
        vocalNode.start(0);
        setMsg("Beat-Lock mode: mastering protected beat...");
        const combined = await off.startRendering();
        try { await ctx.close(); } catch {}
        const mastered = await masterStage(combined, { targetLUFS: lufs });
        const blob = encodeWav(mastered);
        const blobUrl = URL.createObjectURL(blob);
        setPreviewUrl(blobUrl);
        setFinalUrl(blobUrl);
        setMsg("Beat-Lock master ready. Saving to dashboard...");
        const label = (beatStem.name || "BeatLock").replace(/\.[^.]+$/, "") + " - Master";
        uploadErrorRef.current = "";
        const up = await withTimeout(startUpload([new File([blob], label + ".wav", { type: "audio/wav" })]), 240000, "Saving Beat-Lock master");
        const item: any = up && up[0];
        const fileUrl = (item && (item.ufsUrl || item.url)) || (item && item.serverData && (item.serverData.ufsUrl || item.serverData.url)) || "";
        if (!fileUrl) throw new Error("Beat-Lock upload returned no URL: " + (uploadErrorRef.current || "unknown"));
        const save = await fetch("/api/mixes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: label, url: fileUrl }) });
        if (!save.ok) throw new Error("Beat-Lock save failed HTTP " + save.status);
        setTaskId("");
        setMsg("Done - Beat-Lock mastered & saved: " + label);
      } else {
        setMsg("Sending stems to the RoEx engine…");
        const post = await withTimeout(fetch("/api/roex-mix", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stems: done, style }),
        }), 120000, "RoEx request");
        const data = await post.json().catch(() => ({}));
        if (!post.ok || !data.taskId) throw new Error(data.error || "RoEx could not start the mix (code " + post.status + ")");
        setTaskId(data.taskId);

        for (let i = 0; i < 30; i++) {
          setMsg("RoEx is mixing your stems… attempt " + (i + 1) + " of 30");
          await new Promise((r) => setTimeout(r, 5000));
          const s = await fetchWithTimeout("/api/roex-mix?taskId=" + encodeURIComponent(data.taskId), 60000);
          const sd = await s.json().catch(() => ({}));
          if (sd.error) throw new Error(sd.error);
          if (sd.status === "preview" && sd.url) {
            setPreviewUrl(sd.url);
            setMsg("Preview ready — listen below 🎧");
            break;
          }
          if (i === 29) throw new Error("RoEx is taking too long — try again in a minute.");
        }
      }
    } catch (e: any) {
      setErr(e?.name === "AbortError" ? "Connection was too slow and timed out." : (e?.message || "Something went wrong — try again."));
      setMsg("");
    } finally {
      setBusy(false);
    }
  }

  async function unlock() {
    if (!taskId || busy || !prepared.length) return;
    setBusy(true); setErr("");
    try {
      setMsg("Unlocking the full AI mix — this spends credits…");
      const r = await withTimeout(fetch("/api/roex-full", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId, stems: prepared, loudness: roexLoudness }),
      }), 300000, "Full mix");
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Full mix failed");
      let finalR = d && d.url ? d.url : "";
      for (let i = 0; i < 20 && !finalR; i++) {
        setMsg("RoEx is mixing and mastering your song... step " + (i + 1) + " of 20");
        await new Promise((res) => setTimeout(res, 5000));
        const g = await fetchWithTimeout("/api/roex-full?taskId=" + encodeURIComponent(taskId), 60000);
        const gd = await g.json().catch(() => ({}));
        if (gd.error) throw new Error(gd.error);
        if (gd.status === "done" && gd.url) finalR = gd.url;
      }
      if (!finalR) throw new Error("RoEx is taking too long - try again in a minute.");
      setFinalUrl(finalR);
      setMsg("Full mix ready — download below 🎉");
    } catch (e: any) {
      setErr(e?.message || "Full mix failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-blue-200 bg-white p-4">
      <h3 className="text-lg font-bold mb-1">✨ AI Mix &amp; Master (Pro Engine)</h3>
      <p className="text-xs text-gray-500 mb-3">Powered by the RoEx Tonn engine. Preview is free; the full mix uses 1 AI credit.</p>

      <label className="block text-xs font-semibold text-gray-600 mb-1">Musical style</label>
      <select
        value={style}
        onChange={(e) => setStyle(e.target.value)}
        disabled={busy}
        className="w-full mb-3 rounded-lg border border-gray-300 px-3 py-2 text-sm"
      >
        {STYLES.map((s) => (<option key={s.value} value={s.value}>{s.label}</option>))}
      </select>
                <label className="block text-xs font-semibold text-gray-600 mb-1">RoEx master loudness (used on unlock)</label>
        <select value={roexLoudness} onChange={(e) => setRoexLoudness(e.target.value)} disabled={busy} className="w-full mb-3 rounded-lg border border-gray-300 px-3 py-2 text-sm">
          <option value="LOW">LOW — quietest, most dynamic</option>
          <option value="MEDIUM">MEDIUM — balanced, streaming standard</option>
          <option value="HIGH">HIGH — loudest, most competitive</option>
        </select>
<label className="block text-xs font-semibold text-gray-600 mb-1">Beat-Lock loudness (legacy)</label>
        <select value={lufs} onChange={(e) => setLufs(Number(e.target.value))} disabled={busy} className="w-full mb-3 rounded-lg border border-gray-300 px-3 py-2 text-sm">
          <option value={-8}>-8 — Loudest (club)</option>
          <option value={-10}>-10 — Loud</option>
          <option value={-11}>-11 — Balanced</option>
          <option value={-14}>-14 — Streaming calm</option>
        </select>

      <label className="flex items-center gap-2 mb-3 text-xs font-semibold text-gray-600">
        <input type="checkbox" checked={beatLockMode} onChange={(e) => setBeatLockMode(e.target.checked)} disabled={busy} />
        Protect my beat - vocals only go to RoEx
      </label>
      <button
        onClick={generate}
        disabled={!ready || busy}
        className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white disabled:bg-gray-300 disabled:text-gray-500"
      >
        {busy ? "Working…" : "🔊 Generate free AI preview"}
      </button>

      {!ready && (
        <p className="mt-2 text-xs text-gray-500">Add at least 2 stems above (e.g. lead vocal + beat) to unlock the AI engine.</p>
      )}
      {msg && <p className="mt-3 text-xs text-blue-700">{msg}</p>}
      {err && <p className="mt-3 text-xs font-semibold text-red-600">⚠️ {err}</p>}

      {previewUrl && (
        <div className="mt-4">
          <p className="text-xs font-semibold text-gray-600 mb-1">AI preview</p>
          <audio controls src={previewUrl} className="w-full" onTimeUpdate={(e) => { if (isOwner) return; if (e.currentTarget.currentTime > 30) { e.currentTarget.pause(); e.currentTarget.currentTime = 0; } }} />
          {isOwner ? (<a href={previewUrl} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-blue-600 underline">Download full preview</a>) : null}
          {!finalUrl && taskId && (
            <button
              onClick={unlock}
              disabled={busy}
              className="mt-3 w-full rounded-lg bg-black px-4 py-3 text-sm font-semibold text-white disabled:bg-gray-300 disabled:text-gray-500"
            >
              ✨ Unlock full mix + master (uses credits)
            </button>
          )}
        </div>
      )}

      {finalUrl && (
        <div className="mt-4">
          <p className="text-xs font-semibold text-gray-600 mb-1">Full AI mix</p>
          <audio controls src={finalUrl} className="w-full" />
          <a href={finalUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white">⬇️ Open / save full mix</a>
        </div>
      )}

      {busy && <p className="mt-3 text-[11px] text-gray-400">If this stalls over ~3 minutes, reload the page and upload WAV stems — those skip conversion entirely.</p>}
    </div>
  );
}
