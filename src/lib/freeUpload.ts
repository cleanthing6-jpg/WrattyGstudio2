"use client";

import { upload } from "@vercel/blob/client";

// Stem uploads go straight from the browser to Modal (wratty-files app).
// They never pass through a Vercel function, whose request body limit is
// 4.5 MB - smaller than a single stem. Modal accepts up to 4 GiB.
const MODAL_ROOT = "https://wrattyg--wratty-files-web.modal.run";

function sanitizeName(name: string): string {
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  const base = (dot >= 0 ? name.slice(0, dot) : name)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\x20-\x7E]/g, "")
    .replace(/[\[\](){}'"]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return `${base || "stem"}${ext}`;
}

async function putToModal(file: File, key: string): Promise<string> {
  // 1. tiny ticket request to our own route - no file data, so nothing close
  //    to the 4.5 MB function body limit.
  const t = await fetch("/api/stem-ticket", {
    method: "POST",
    cache: "no-store",
  });
  if (!t.ok) throw new Error("ticket request failed: " + t.status);
  const { ticket, uploadUrl } = await t.json();
  const root = String(uploadUrl || MODAL_ROOT).replace(/\/+$/, "");

  // 2. the file itself goes browser -> Modal, bypassing Vercel entirely
  const path = key.split("/").map(encodeURIComponent).join("/");
  const r = await fetch(`${root}/u/${path}`, {
    method: "PUT",
    headers: {
      "x-fx-ticket": ticket,
      "content-type": file.type || "application/octet-stream",
    },
    body: file,
  });
  if (!r.ok) {
    throw new Error(`modal upload ${r.status}: ${(await r.text()).slice(0, 200)}`);
  }
  const j = await r.json();
  if (!j?.url) throw new Error("modal upload returned no url");
  return j.url as string;
}

// Same signature and same return type as before: callers expect a string.
export async function uploadStem(
  file: File,
  folder: "stems" | "masters" = "stems",
): Promise<string> {
  if (!file || file.size === 0) {
    throw new Error("Cannot upload an empty file");
  }
  const name = sanitizeName(file.name) || "stem.wav";
  const key = `${folder}/${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}-${name}`;

  try {
    return await putToModal(file, key);
  } catch (e) {
    // Kept so a Modal outage can't brick uploads entirely. It will fail too
    // while Vercel is paused - that's expected, the error is logged below.
    console.warn("[uploadStem] Modal upload failed, falling back to Blob:", e);
    const blob = await upload(key, file, {
      access: "public",
      handleUploadUrl: "/api/blob-upload",
      multipart: true,
    });
    return blob.url;
  }
}
