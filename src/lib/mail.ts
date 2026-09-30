import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);
const FROM = process.env.MAIL_FROM || "Wratty <onboarding@resend.dev>";

// Renders are async and can take minutes. Every send is best-effort: a mail
// failure must never break the render or the API response.
export async function sendRenderEmail(
  to: string,
  status: "ready" | "failed",
  opts?: { url?: string; error?: string; charged?: boolean }
) {
  if (!to || !process.env.RESEND_API_KEY) return;
  const ready = status === "ready";
  try {
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
