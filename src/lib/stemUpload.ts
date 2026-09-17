"use client";
import { upload } from "@vercel/blob/client";

export type StemUpload = { url: string; name: string; contentType: string };

export async function uploadStem(file: File, role = "stem"): Promise<StemUpload> {
  const safe = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
  const blob = await upload(`stems/${role}-${Date.now()}-${safe}`, file, {
    access: "public",
    handleUploadUrl: "/api/blob-upload",
    multipart: true,
    clientPayload: JSON.stringify({ role }),
  });
  return { url: blob.url, name: file.name, contentType: file.type };
}
