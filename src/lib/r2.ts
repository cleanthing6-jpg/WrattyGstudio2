import { S3Client } from "@aws-sdk/client-s3";

export const r2 = new S3Client({
  region: "olas-closet",
  endpoint: "https://s3.rumptycloud.com",
  forcePathStyle: true,
  credentials: {
    accessKeyId: process.env.RUMPTY_ACCESS_KEY_ID || "",
    secretAccessKey: process.env.RUMPTY_SECRET_ACCESS_KEY || "",
  },
});

export const R2_BUCKET = process.env.RUMPTY_BUCKET_NAME || "";
