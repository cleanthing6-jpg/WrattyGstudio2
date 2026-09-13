#!/usr/bin/env node
const BASE = "https://tonn.roexaudio.com";
const KEY = process.env.ROEX_API_KEY || "";
const id = process.argv[2];
if (!id) { console.error("Usage: ROEX_API_KEY=... node probe.mjs <taskId>"); process.exit(1); }
const H = { "x-api-key": KEY, "Content-Type": "application/json" };
const q = encodeURIComponent(id);

const tests = [
  ["GET",  "/masteringstatus/" + id, null],
  ["GET",  "/previewmasterstatus/" + id, null],
  ["GET",  "/mixstatus/" + id, null],
  ["GET",  "/masteringstatus?mastering_task_id=" + q, null],
  ["POST", "/masteringstatus", { mastering_task_id: id }],
  ["POST", "/masteringstatus", { masteringTaskId: id }],
  ["POST", "/retrievemasteringpreview", { mastering_task_id: id }],
  ["POST", "/retrievemasteringpreview", { masteringTaskId: id }],
  ["POST", "/retrievemaster", { mastering_task_id: id }],
];

for (const [method, path, body] of tests) {
  try {
    const r = await fetch(BASE + path, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
    const t = await r.text();
    console.log("[" + r.status + "] " + method + " " + path + (body ? " " + JSON.stringify(body) : ""));
    console.log("     " + t.replace(/\s+/g, " ").slice(0, 280));
  } catch (e) {
    console.log("[ERR] " + method + " " + path + " -> " + e.message);
  }
}
console.log("done");
