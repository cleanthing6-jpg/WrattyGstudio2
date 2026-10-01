import crypto from "crypto";

// Mints the short-lived ticket that the Modal "wratty-files" app verifies on
// /f/ and /ls. The shared secret never reaches the browser: the ticket is
// created server-side and sent as a header on our own upstream fetches.
export function fxTicket(scope: string, ttlSec = 600): string {
  const key = process.env.FX_INTERNAL_SECRET || "";
  if (!key) return "";
  const exp = Math.floor(Date.now() / 1000) + ttlSec;
  const sig = crypto.createHmac("sha256", key).update(`${scope}|${exp}`).digest("hex");
  return `${exp}.${sig}`;
}
