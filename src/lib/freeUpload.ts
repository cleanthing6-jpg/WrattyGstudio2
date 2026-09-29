"use client";

// All audio goes browser -> Cloudflare R2 via a presigned PUT.
// Render never touches the bytes: we only sign, the browser sends the file.

type Folder = "stems" | "masters";

type Signed = { url: string; key: string; id: string; getUrl?: string };

async function signUpload(name: string, type: string, folder: Folder): Promise<Signed> {
  const r = await fetch("/api/upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ name, type, folder }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j?.url) {
    throw new Error("Could not sign upload: " + (j?.error || r.status));
  }
  return j as Signed;
}

// Same signature as before: callers expect a string URL.
export async function uploadStem(
  file: File,
  folder: Folder = "stems",
): Promise<string> {
  if (!file || file.size === 0) {
    throw new Error("Cannot upload an empty file");
  }

  const type = file.type || "application/octet-stream";
  const { url, id, getUrl } = await signUpload(file.name, type, folder);

  const put = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": type },
    body: file,
  });
  if (!put.ok) {
    throw new Error(`R2 upload ${put.status}: ${(await put.text()).slice(0, 200)}`);
  }

  // Absolute https URL. Prefer the presigned GET so a non-browser caller
  // (the mix engine) can fetch it without a session cookie.
  if (getUrl) return getUrl;
  return `${window.location.origin}/api/file?id=${encodeURIComponent(id)}`;
}
