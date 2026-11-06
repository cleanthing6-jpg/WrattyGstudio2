import { NextResponse } from "next/server";
import { Resend } from "resend";
import { currentUser } from "@clerk/nextjs/server";

const resend = new Resend(process.env.RESEND_API_KEY);

export async function POST(req: Request) {
  try {
    const { subject, message } = await req.json();

    if (!subject || !message) {
      return NextResponse.json({ error: "Subject and message are required" }, { status: 400 });
    }

    const user = await currentUser();
    const userEmail = user?.primaryEmailAddress?.emailAddress || "";
    const userName = user?.firstName || "Developer";

    if (!userEmail) {
      return NextResponse.json({ error: "Your account does not have an email address." }, { status: 400 });
    }

    // REPLACE THIS WITH YOUR ACTUAL EMAIL ADDRESS
    const YOUR_EMAIL = "wrattyg@gmail.com"; 

    const { data, error } = await resend.emails.send({
      from: "WraGstudio Support <onboarding@resend.dev>",
      to: [YOUR_EMAIL],
      reply_to: userEmail, // <--- THIS IS THE MAGIC FIX
      subject: `[API Support] ${subject}`,
      html: `
        <div style="font-family: sans-serif; padding: 20px; color: #333;">
          <h2 style="color: #22c55e;">New Developer Support Request</h2>
          <p><strong>From:</strong> ${userName} (<a href="mailto:${userEmail}">${userEmail}</a>)</p>
          <p><strong>Subject:</strong> ${subject}</p>
          <hr style="border: 1px solid #eee; margin: 20px 0;" />
          <p style="white-space: pre-wrap;">${message}</p>
        </div>
      `,
    });

    if (error) {
      console.error("Resend error:", error);
      return NextResponse.json({ error: error.message || "Failed to send email" }, { status: 500 });
    }

    return NextResponse.json({ success: true, data });
  } catch (error: any) {
    console.error("Support route error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
