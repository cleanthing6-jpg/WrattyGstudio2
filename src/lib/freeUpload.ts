"use client";

import { upload } from "@vercel/blob/client";

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

export async function uploadStem(file: File): Promise<string> {
  if (!file || file.size === 0) {
    throw new Error("Cannot upload an empty file");
  }
  const name = sanitizeName(file.name) || "stem.wav";
  const blob = await upload(`stems/${Date.now()}-${name}`, file, {
    access: "public",
    handleUploadUrl: "/api/blob-upload",
    multipart: true,
  });
  return blob.url; // callers expect a string
}
