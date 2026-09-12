// Browser -> free temporary host -> public URL. No account, no UploadThing.
export async function uploadStem(file: File): Promise<string> {
  // 1) litterbox (catbox temporary): 1 hour, up to 1GB, no account
  try {
    const fd = new FormData();
    fd.append("reqtype", "fileupload");
    fd.append("time", "1h");
    fd.append("fileToUpload", file, file.name);
    const r = await fetch("https://litterbox.catbox.moe/resources/internals/api.php", { method: "POST", body: fd });
    const t = (await r.text()).trim();
    if (r.ok && t.indexOf("http") === 0) return t;
  } catch (e) {
    console.warn("[freeUpload] litterbox failed", e);
  }
  // 2) tmpfiles.org fallback: 100MB, 1 hour
  try {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const r = await fetch("https://tmpfiles.org/api/v1/upload", { method: "POST", body: fd });
    const j: any = await r.json().catch(() => ({}));
    const u: string = (j && j.data && j.data.url) || "";
    if (r.ok && u.indexOf("http") === 0) return u.replace("tmpfiles.org/", "tmpfiles.org/dl/");
  } catch (e) {
    console.warn("[freeUpload] tmpfiles failed", e);
  }
  throw new Error("Upload failed: both free hosts refused. Check your connection and try again.");
}
