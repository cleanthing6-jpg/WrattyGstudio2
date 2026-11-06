import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const user = await currentUser();
    const email = user?.primaryEmailAddress?.emailAddress;
    if (!email) return NextResponse.json({ error: "No email" }, { status: 400 });

    // Ensure they have a developer profile
    const client = await getMongoClient();
    const db = client.db();
    const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
    
    if (!profile) {
      return NextResponse.json({ error: "Please complete your company verification first." }, { status: 403 });
    }

    const body = await req.json();
    const packageType = body.packageType || "mix";

    // Approximate NGN conversion for Paystack (Paystack requires NGN)
    // 1 USD ≈ 1,500 NGN (Adjust this based on your actual pricing)
    let amountNGN = 0;
    let credits = 0;

    if (packageType === "master") {
      amountNGN = 1000 * 1500; // $1,000 -> ₦1,500,000
      credits = 1000;
    } else {
      amountNGN = 2500 * 1500; // $2,500 -> ₦3,750,000
      credits = 1000;
    }

    const priceInKobo = amountNGN * 100; 
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
          credits: credits,
          company: profile.companyName,
          packageType: packageType
        },
      }),
    });

    const data = await response.json();
    
    // Pass the exact Paystack error message to the frontend
    if (!data.status) {
      return NextResponse.json({ error: data.message || "Paystack rejected the transaction" }, { status: 500 });
    }

    return NextResponse.json({ url: data.data.authorization_url });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || "Internal Server Error" }, { status: 500 });
  }
}
