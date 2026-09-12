import { uploadFiles } from "@/utils/uploadthing";

export async function uploadStem(file: File): Promise<string> {
  const res = await uploadFiles("audioUploader", { files: [file] });
  const f: any = res && res[0];
  const sd: any = (f && f.serverData) || {};
  const url = (f && (f.url || f.ufsUrl || sd.url || sd.ufsUrl)) || "";
  if (!url) throw new Error("UploadThing returned no file URL");
  return url;
}
