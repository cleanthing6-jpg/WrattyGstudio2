import { Resend } from "resend";

const FROM = process.env.MAIL_FROM || "Wratty <onboarding@resend.dev>";

// Lazy: never construct at module scope, or `next build` fails while Next
// collects page data for every route (no key at build time).
export async function sendRenderEmail(
  to: string,
  status: "ready" | "failed",
  opts?: { url?: string; error?: string; charged?: boolean }
) {
  const key = process.env.RESEND_API_KEY;
  if (!to || !key) return;

  const ready = status === "ready";
  try {
    const resend = new Resend(key);
    await resend.emails.send({
      from: FROM,
      to: [to],
      subject: ready ? "Your master is ready 🎧" : "Your render could not finish",
      text: ready
        ? `Your mix is done.\n\nDownload: ${opts?.url || ""}\n\nThe link expires — grab it soon.`
        : `Your render failed.\n\nReason: ${opts?.error || "unknown"}\n\n` +
          (opts?.charged === false
            ? "You were not charged a credit."
            : "Check your credits — if you were charged, reply and we'll fix it."),
    });
  } catch (e) {
    console.error("[mail] send failed", e);
  }
}
