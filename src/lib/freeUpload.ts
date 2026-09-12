const CHUNK = 3000000;
const TRIES = 3;

async function sendPart(url: string, slice: Blob) {
  for (let attempt = 1; attempt <= TRIES; attempt++) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: slice,
      });
      const j: any = await r.json().catch(() => ({}));
      if (r.ok) return { ok: true, url: (j && j.url) || "", error: "" };
      const retryable = r.status === 408 || r.status === 429 || r.status >= 500;
      if (!retryable || attempt === TRIES) {
        return { ok: false, url: "", error: (j && j.error) || ("HTTP " + r.status) };
      }
    } catch (e: any) {
      if (attempt === TRIES) return { ok: false, url: "", error: (e && e.message) || "network error" };
    }
    await new Promise((res) => setTimeout(res, attempt * 1500));
  }
  return { ok: false, url: "", error: "unknown" };
}

export async function uploadStem(file: File): Promise<string> {
  const size = Math.max(1, file.size);
  const total = Math.max(1, Math.ceil(size / CHUNK));
  const uploadId = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  let url = "";
  for (let i = 0; i < total; i++) {
    const slice = file.slice(i * CHUNK, Math.min((i + 1) * CHUNK, size));
    const qs = new URLSearchParams({ uploadId, name: file.name, index: String(i), total: String(total) });
    const res = await sendPart("/api/stem-upload?" + qs.toString(), slice);
    if (!res.ok) throw new Error("Upload failed on part " + (i + 1) + " of " + total + ": " + (res.error || "unknown"));
    if (res.url) url = res.url;
  }
  if (!url) throw new Error("Upload finished but no file URL came back");
  return url;
}
