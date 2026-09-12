import { uploadFiles } from "@/utils/uploadthing";

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

  const safeFile = new File([file], sanitizeName(file.name), { type: file.type });

  const res = await uploadFiles("audioUploader", { files: [safeFile] });
  const f: any = res && res[0];
  const sd: any = (f && f.serverData) || {};
  const url = (f && (f.url || f.ufsUrl || sd.url || sd.ufsUrl)) || "";
  if (!url) throw new Error("UploadThing returned no file URL");
  return url;
}
