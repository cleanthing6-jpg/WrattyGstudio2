import { createUploadthing, type FileRouter } from "uploadthing/next";
import { getAuth } from "@clerk/nextjs/server";

const f = createUploadthing();

export const ourFileRouter = {
  audioUploader: f({ blob: { maxFileSize: "128MB", maxFileCount: 1 } })
    .middleware(async ({ req }: any) => {
      try {
        const { userId } = getAuth(req as any);
        return { userId: userId ?? null };
      } catch (e) {
        return { userId: null };
      }
    })
    .onUploadComplete(async ({ file }: any) => {
      const anyFile: any = file;
      const url = anyFile.ufsUrl || anyFile.url || "";
      console.log("[UPLOAD] stored " + (anyFile.name || "?") + " -> " + url.slice(0, 90));
      return { url };
    }),
  imageUploader: f({ image: { maxFileSize: "8MB", maxFileCount: 3 } })
    .onUploadComplete(async ({ file }: any) => {
      const anyFile: any = file;
      return { url: anyFile.ufsUrl || anyFile.url || "" };
    }),
};

export type OurFileRouter = typeof ourFileRouter;
