import { UTApi } from "uploadthing/server";
import fs from "node:fs";

for (const f of [".env.local", ".env"]) {
  if (!fs.existsSync(f)) continue;
  for (const line of fs.readFileSync(f, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const utapi = new UTApi();
let all = [];
let offset = 0;
while (true) {
  const res = await utapi.listFiles({ limit: 500, offset });
  const files = res.files ?? res;
  all = all.concat(files);
  if (!files || files.length < 500) break;
  offset += 500;
}

const MB = (n) => ((n || 0) / 1048576).toFixed(1) + " MB";
const total = all.reduce((s, f) => s + (f.size || 0), 0);
console.log(`Total files: ${all.length}`);
console.log(`Total size: ${(total / 1073741824).toFixed(2)} GB\n`);

all.sort((a, b) => (b.size || 0) - (a.size || 0));
console.log("Biggest 20:");
for (const f of all.slice(0, 20)) {
  console.log(`  ${MB(f.size).padStart(10)}  ${String(new Date(f.uploadedAt).toISOString()).slice(0,10)}  ${f.name}`);
}

if (process.env.DELETE === "1") {
  const keep = Number(process.env.KEEP || 20);
  const byAge = [...all].sort((a, b) => new Date(a.uploadedAt) - new Date(b.uploadedAt));
  const toDelete = byAge.slice(0, Math.max(0, byAge.length - keep));
  console.log(`\nDeleting ${toDelete.length} files (keeping newest ${keep})...`);
  const keys = toDelete.map((f) => f.key);
  for (let i = 0; i < keys.length; i += 100) {
    await utapi.deleteFiles(keys.slice(i, i + 100));
    console.log(`  ${Math.min(i + 100, keys.length)}/${keys.length}`);
  }
  console.log("Freed:", MB(toDelete.reduce((s, f) => s + (f.size || 0), 0)));
} else {
  console.log("\n--- DRY RUN --- nothing deleted.");
  console.log("To delete old files:  DELETE=1 KEEP=20 node cleanup-ut.mjs");
}
