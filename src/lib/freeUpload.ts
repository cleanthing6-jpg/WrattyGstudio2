const CHUNK = 700000;

function b64(buf: ArrayBuffer) {
  const b = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s);
}

export async function uploadStem(file: File): Promise<string> {
  const size = Math.max(1, file.size);
  const total = Math.max(1, Math.ceil(size / CHUNK));
  const uploadId = Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  let url = "";
  for (let i = 0; i < total; i++) {
    const slice = file.slice(i * CHUNK, Math.min((i + 1) * CHUNK, size));
    const body = JSON.stringify({
      uploadId: uploadId,
      name: file.name,
      index: i,
      total: total,
      data: b64(await slice.arrayBuffer()),
    });
    let done = false;
    for (let a = 1; a <= 3 && !done; a++) {
      try {
        const ctrl = new AbortController();
        const kill = setTimeout(() => ctrl.abort(), 90000);
        const r = await fetch("/api/stem-upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
          signal: ctrl.signal,
        });
        clearTimeout(kill);
        const j: any = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error((j && j.error) || ("HTTP " + r.status));
        if (j && j.url) url = j.url;
        done = true;
      } catch (e: any) {
        if (a === 3) throw new Error("Upload failed on part " + (i + 1) + " of " + total + ": " + (e && e.message));
        await new Promise((res) => setTimeout(res, a * 1500));
      }
    }
  }
  if (!url) throw new Error("Upload finished but no file URL came back");
  return url;
}
