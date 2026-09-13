#!/usr/bin/env node
import { writeFile } from "node:fs/promises";
const BASE = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";
const id = process.argv[2];
const out = process.argv[3] || "";
if (!id) { console.error("Usage: ROEX_API_KEY=... node getmaster.mjs <taskId> [outputPath]"); process.exit(1); }

const r = await fetch(BASE + "/masteringstatus/" + id, { headers: { "x-api-key": KEY } });
const t = await r.text();
let d; try { d = JSON.parse(t); } catch { d = { raw: t }; }

const td = d.mastering_task_data || d;
console.log("state:", td.state || td.status || "(none)");

const url = td.download_url_mastered || td.download_url_mastered_preview || td.download_url || td.url || "";
if (!url) { console.log("No master URL. Raw:", JSON.stringify(d).slice(0, 600)); process.exit(1); }
console.log("\nMASTER URL:\n" + url);

if (out) {
  const a = await fetch(url);
  if (!a.ok) { console.error("Download failed: HTTP " + a.status); process.exit(1); }
  const buf = Buffer.from(await a.arrayBuffer());
  await writeFile(out, buf);
  console.log("\nSaved " + (buf.length / 1048576).toFixed(1) + " MB -> " + out);
}
