import { createUploadthing, type FileRouter } from "uploadthing/next";
import { getAuth } from "@clerk/nextjs/server";
import clientPromise from "@/lib/mongodb";

const f = createUploadthing();

export const ourFileRouter = {
  audioUploader: f({ blob: { maxFileSize: "64MB", maxFileCount: 1 } })
    .middleware(async ({ req }: any) => {
      try {
        const { userId } = getAuth(req as any);
        return { userId: userId ?? null };
      } catch (e) {
        return { userId: null };
      }
    })
    .onUploadComplete(async ({ metadata, file }: any) => {
      const anyFile: any = file;
      const url = anyFile.ufsUrl || anyFile.url || "";
      const isMaster = / - Master\.wav$/i.test(anyFile.name || "");
      if (metadata && metadata.userId && isMaster && url) {
        try {
          const client = await clientPromise;
          await client
            .db("wrattyg")
            .collection("mixes")
            .updateOne(
              { userId: metadata.userId, url },
              { $setOnInsert: { userId: metadata.userId, name: String(anyFile.name).replace(/\.[^.]+$/, ""), url, createdAt: new Date() } },
              { upsert: true }
            );
        } catch (e) {
          console.error("Master save error:", e);
        }
      }
      return { url };
    }),
  imageUploader: f({ image: { maxFileSize: "8MB", maxFileCount: 3 } })
    .onUploadComplete(async ({ file }: any) => {
      const anyFile: any = file;
      return { url: anyFile.ufsUrl || anyFile.url || "" };
    }),
};

export type OurFileRouter = typeof ourFileRouter;
