import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const user = await currentUser();
  const email = user?.primaryEmailAddress?.emailAddress;
  if (!email) return NextResponse.json({ error: "No email" }, { status: 400 });

  // Amount in kobo (Naira) or cents (USD). $2,500 = 250,000 cents.
  // Paystack international payments usually require setting currency properly.
  const priceInKobo = 250000 * 100; // Adjust for Naira conversion if needed

  const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
  const callbackUrl = new URL("/developers", appUrl).toString();

  const response = await fetch("https://api.paystack.co/transaction/initialize", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.PAYSTACK_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      amount: priceInKobo,
      currency: "NGN", // Change to "USD" if your Paystack account supports it
      callback_url: callbackUrl,
      metadata: {
        type: "api_credits", // This is CRUCIAL for the webhook
        userId: userId,
        credits: 1000,
      },
    }),
  });

  const data = await response.json();
  if (!data.status) return NextResponse.json({ error: "Paystack error" }, { status: 500 });

  return NextResponse.json({ url: data.data.authorization_url });
}
