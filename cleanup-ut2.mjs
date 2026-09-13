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
let all = [], offset = 0;
while (true) {
  const res = await utapi.listFiles({ limit: 500, offset });
  const files = res.files ?? res;
  all = all.concat(files);
  if (!files || files.length < 500) break;
  offset += 500;
}

const MB = (n) => ((n || 0) / 1048576).toFixed(1) + " MB";

const byName = new Map();
for (const f of all) {
  const prev = byName.get(f.name);
  if (!prev || new Date(f.uploadedAt) > new Date(prev.uploadedAt)) byName.set(f.name, f);
}
const keep = new Set([...byName.values()].map((f) => f.key));
const dups = all.filter((f) => !keep.has(f.key));

console.log(`Total: ${all.length} files, ${(all.reduce((s,f)=>s+(f.size||0),0)/1073741824).toFixed(2)} GB`);
console.log(`Unique names: ${byName.size}`);
console.log(`Duplicate copies: ${dups.length}, freeing ~${MB(dups.reduce((s,f)=>s+(f.size||0),0))}`);

if (process.env.DELETE === "1") {
  const keys = dups.map((f) => f.key);
  for (let i = 0; i < keys.length; i += 100) {
    await utapi.deleteFiles(keys.slice(i, i + 100));
    console.log(`  deleted ${Math.min(i + 100, keys.length)}/${keys.length}`);
  }
  console.log("Done.");
} else {
  console.log("\nDRY RUN. To delete duplicates:  DELETE=1 node cleanup-ut2.mjs");
}
