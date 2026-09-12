// Browser -> our own server, in small pieces -> assembled and served back as a URL.
const CHUNK = 1800000;

function toB64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  const step = 8192;
  for (let i = 0; i < bytes.length; i += step) {
    const part = bytes.subarray(i, Math.min(i + step, bytes.length));
    s += String.fromCharCode.apply(null, Array.prototype.slice.call(part));
  }
  return btoa(s);
}

export async function uploadStem(file: File): Promise<string> {
  const size = Math.max(1, file.size);
  const total = Math.max(1, Math.ceil(size / CHUNK));
  const uploadId = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  let url = "";
  for (let i = 0; i < total; i++) {
    const slice = file.slice(i * CHUNK, Math.min((i + 1) * CHUNK, size));
    const data = toB64(await slice.arrayBuffer());
    const r = await fetch("/api/stem-upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uploadId, name: file.name, index: i, total, data }),
    });
    const j: any = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((j && j.error) || ("Upload failed on part " + (i + 1) + " of " + total + " (HTTP " + r.status + ")"));
    if (j && j.url) url = j.url;
  }
  if (!url) throw new Error("Upload finished but no file URL came back");
  return url;
}
