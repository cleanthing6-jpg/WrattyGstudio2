import { Resend } from "resend";

const RESEND_KEY = process.env.RESEND_API_KEY || "";
const FROM = process.env.MAIL_FROM || "";
const OWNER = (process.env.OWNER_USER_ID || "").trim();

// Global throttle: at most ONE operational alert per hour. An alert storm is
// worse than a missed alert, and Resend's free tier is shared with the
// customer render emails.
let lastSent = 0;
let suppressed = 0;

async function ownerAddress(): Promise<string> {
  if (!OWNER) return "";
  try {
    const mod: any = await import("@clerk/nextjs/server");
    const cc: any =
      typeof mod.clerkClient === "function" ? await mod.clerkClient() : mod.clerkClient;
    const u = await cc.users.getUser(OWNER);
    return u?.emailAddresses?.[0]?.emailAddress || "";
  } catch {
    return "";
  }
}

/**
 * Best-effort operational alert. NEVER throws: an alerting failure must not
 * break a render, a refund, or the retention sweep. Throttled to one email
 * per hour, with a suppressed count so nothing is silently lost.
 */
export async function sendAlert(subject: string, text: string): Promise<void> {
  try {
    const now = Date.now();
    if (now - lastSent < 60 * 60 * 1000) {
      suppressed++;
      console.warn("[alert] suppressed (throttled):", subject);
      return;
    }
    if (!RESEND_KEY || !FROM) {
      console.warn("[alert] RESEND_API_KEY or MAIL_FROM missing; log only:", subject, text);
      return;
    }
    const to = await ownerAddress();
    if (!to) {
      console.warn("[alert] no owner email; log only:", subject, text);
      return;
    }
    const extra = suppressed
      ? "\n\n(" + suppressed + " similar alert(s) suppressed in the last hour)"
      : "";
    lastSent = now;
    suppressed = 0;
    const r = new Resend(RESEND_KEY);
    await r.emails.send({
      from: FROM,
      to,
      subject: "[WrattyGstudio] " + subject,
      text: text + extra,
    });
  } catch (e: any) {
    console.error("[alert] failed (ignored):", e?.message || e);
  }
}
