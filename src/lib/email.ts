import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY);

export async function sendMixReadyEmail(to: string, name: string, songTitle: string) {
  try {
    await resend.emails.send({
      from: "WraGstudio <hello@wrattygstudio2.zevcloud.app>",
      to,
      html: `
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
          <h2>Hey ${name},</h2>
          <p>Your mix and master for <strong>"${songTitle}"</strong> is finished!</p>
          <p>Listen to your track and unlock the full high-quality download here:</p>
          <a href="https://wrattygstudio2.zevcloud.app/dashboard" style="display: inline-block; background-color: #22c55e; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 16px;">
            Listen to Your Mix
          </a>
          <p style="margin-top: 24px; color: #666; font-size: 14px;">— The WraGstudio Team</p>
        </div>
      `,
    });
    console.log(`Email sent to ${to}`);
  } catch (error) {
    console.error("Failed to send email:", error);
  }
}