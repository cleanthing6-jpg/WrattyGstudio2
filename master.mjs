#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";

const BASE = "https://tonn.roexaudio.com";
const MIME = { wav: "audio/wav", mp3: "audio/mpeg", flac: "audio/flac" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pick = (o, ks) => ks.map((k) => o && o[k]).find(Boolean) || "";

async function getKey() {
  if (process.env.ROEX_API_KEY) return process.env.ROEX_API_KEY.trim();
  const t = await readFile(".env.local", "utf8").catch(() => "");
  const m = t.match(/^\s*ROEX_API_KEY\s*=\s*["']?([^"'\r\n]+)/m);
  return m ? m[1].trim() : "";
}

const apiKey = await getKey();
if (!apiKey) { console.error("ROEX_API_KEY missing"); process.exit(1); }
const H = { "x-api-key": apiKey, "Content-Type": "application/json" };

const call = async (path, { method = "POST", body } = {}) => {
  const r = await fetch(BASE + path, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  let d; try { d = t ? JSON.parse(t) : {}; } catch { d = { raw: t.slice(0, 400) }; }
  return { ok: r.ok, status: r.status, data: d };
};

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith("--"));
const si = process.argv.indexOf("--save");
const outPath = si >= 0 ? (process.argv[si + 1] || "/sdcard/Download/RoEx_Final_Master.wav") : "";
if (!file) { console.error("Usage: node master.mjs <file.wav> [--save [outPath]]"); process.exit(1); }

const base = file.split("/").pop().replace(/\s+\(\d+\)$/, "");
const m = base.match(/^(.*)\.(wav|wave|mp3|flac)$/i);
if (!m) { console.error("Accepts .wav / .wave / .mp3 / .flac"); process.exit(1); }
const ext = m[2].toLowerCase() === "wave" ? "wav" : m[2].toLowerCase();
const filename = m[1] + "." + ext;

const bytes = await readFile(file);
console.log("File: " + filename + " (" + (bytes.length / 1048576).toFixed(1) + " MB)");

const slot = await call("/upload", { body: { filename, contentType: MIME[ext] } });
if (!slot.ok) { console.error("Upload slot failed " + slot.status + ": " + JSON.stringify(slot.data)); process.exit(1); }
const signed = pick(slot.data, ["signed_url", "signedUrl"]);
const readable = pick(slot.data, ["readable_url", "readableUrl", "fileUrl"]);
if (!signed || !readable) { console.error("No upload URLs: " + JSON.stringify(slot.data)); process.exit(1); }

const put = await fetch(signed, { method: "PUT", headers: { "Content-Type": MIME[ext] }, body: bytes });
if (!put.ok) { console.error("Byte upload failed: HTTP " + put.status); process.exit(1); }
console.log("Uploaded. Submitting mastering...");

const shapes = [
  { trackData: [{ trackURL: readable }], musicalStyle: "AFROBEAT", desiredLoudness: "MEDIUM" },
  { trackData: { trackURL: readable }, musicalStyle: "AFROBEAT", desiredLoudness: "MEDIUM" },
  { masteringData: { trackData: [{ trackURL: readable }], musicalStyle: "AFROBEAT", desiredLoudness: "MEDIUM" } },
];
let job = null;
for (const body of shapes) {
  job = await call("/masteringpreview", { body });
  if (job.ok) break;
  if (!/JSON format not valid|required/i.test(JSON.stringify(job.data || {}))) break;
}

const taskId = pick(job && job.data, ["mastering_task_id", "masteringTaskId", "taskId", "task_id"]);
if (!taskId) { console.error("No task id (" + job.status + "): " + JSON.stringify(job.data)); process.exit(1); }
console.log("Mastering task: " + taskId);

let url = "";
for (let i = 1; i <= 120 && !url; i++) {
  const s = await call("/masteringstatus/" + taskId, { method: "GET" });
  const td = (s.data && s.data.mastering_task_data) || s.data || {};
  const st = String(pick(td, ["state", "status"])).toLowerCase();
  if (/fail|error/.test(st)) { console.error("RoEx failed: " + JSON.stringify(s.data)); process.exit(1); }
  url = pick(td, ["download_url_mastered", "download_url", "master_url", "url"]);
  if (!url) { console.log("  " + (st || "waiting") + " (" + i + "/120)"); await sleep(10000); }
}

if (!url) { console.error("No master yet. Check later: node getmaster.mjs " + taskId); process.exit(1); }
console.log("\nMASTER URL:\n" + url);

if (outPath) {
  const a = await fetch(url);
  const buf = Buffer.from(await a.arrayBuffer());
  await writeFile(outPath, buf);
  console.log("\nSaved " + (buf.length / 1048576).toFixed(1) + " MB -> " + outPath);
}
