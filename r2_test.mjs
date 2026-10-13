import { readFileSync } from "node:fs";
import {
  S3Client, PutObjectCommand, GetObjectCommand,
  ListObjectsV2Command, DeleteObjectCommand,
} from "@aws-sdk/client-s3";

const env = Object.fromEntries(
  readFileSync(".env.local", "utf8")
    .split("\n")
    .filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
    })
);

const Bucket = env.R2_BUCKET_NAME;
const r2 = new S3Client({
  region: "auto",
  endpoint: `https://${env.CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.CLOUDFLARE_R2_ACCESS_KEY_ID,
    secretAccessKey: env.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
  },
});

console.log("bucket  :", Bucket);
console.log("endpoint:", `https://${env.CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com`);

const Key = `test/hello-${Date.now()}.txt`;

try {
  await r2.send(new PutObjectCommand({
    Bucket, Key, Body: "wratty r2 test", ContentType: "text/plain",
  }));
  console.log("PUT     ok");

  const got = await r2.send(new GetObjectCommand({ Bucket, Key }));
  let text = "";
  for await (const chunk of got.Body) text += chunk;
  console.log("GET     ok ->", text);

  const list = await r2.send(new ListObjectsV2Command({ Bucket, Prefix: "test/" }));
  console.log("LIST    ok ->", (list.Contents || []).map((o) => o.Key).join(", "));

  await r2.send(new DeleteObjectCommand({ Bucket, Key }));
  console.log("DELETE  ok");

  console.log("\nR2 IS WORKING ✅");
} catch (e) {
  console.error("\nR2 FAILED ❌");
  console.error(e.name + ": " + e.message);
  process.exit(1);
}
