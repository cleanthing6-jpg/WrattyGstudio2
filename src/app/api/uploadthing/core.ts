import { createUploadthing, type FileRouter } from "uploadthing/next";

const f = createUploadthing();

export const ourFileRouter = {
  audioUploader: f({ blob: { maxFileSize: "64MB", maxFileCount: 1 } })
    .onUploadComplete(async ({ file }) => {
      return { url: file.ufsUrl };
    }),
  imageUploader: f({ image: { maxFileSize: "8MB", maxFileCount: 3 } })
    .onUploadComplete(async ({ file }) => {
      return { url: file.ufsUrl };
    }),
} satisfies FileRouter;

export type OurFileRouter = typeof ourFileRouter;
