import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const user = await currentUser();
  const email = user?.primaryEmailAddress?.emailAddress;
  if (!email) return NextResponse.json({ error: "No email" }, { status: 400 });

  // Block free email providers (Gmail, Yahoo, etc.)
  const freeEmails = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"];
  const domain = email.split("@")[1];
  if (freeEmails.includes(domain)) {
    return NextResponse.json({ error: "Please use a business email address." }, { status: 403 });
  }

  // Ensure they have a developer profile
  const client = await getMongoClient();
  const db = client.db();
  const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
  
  if (!profile) {
    return NextResponse.json({ error: "Please complete your company verification first." }, { status: 403 });
  }

  const priceInKobo = 250000 * 100; 
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
      currency: "NGN", 
      callback_url: callbackUrl,
      metadata: {
        type: "api_credits",
        userId: userId,
        credits: 1000,
        company: profile.companyName,
      },
    }),
  });

  const data = await response.json();
  if (!data.status) return NextResponse.json({ error: "Paystack error" }, { status: 500 });

  return NextResponse.json({ url: data.data.authorization_url });
}
