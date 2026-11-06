import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    // Ensure they have a developer profile
    const client = await getMongoClient();
    const db = client.db();
    const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
    
    if (!profile) {
      return NextResponse.json({ error: "Please complete your company verification first." }, { status: 403 });
    }

    const body = await req.json();
    const packageType = body.packageType || "mix";

    let amountUSD = 0;
    if (packageType === "master") {
      amountUSD = 1000;
    } else {
      amountUSD = 2500;
    }

    const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
    
    // --- REPLACE THIS WITH YOUR CRYPTO PROVIDER API ---
    // Example: Breet, StableFlow, etc.
    // const providerRes = await fetch("https://api.yourprovider.com/v1/checkout", {
    //   method: "POST",
    //   headers: { Authorization: `Bearer ${process.env.CRYPTO_API_KEY}`, "Content-Type": "application/json" },
    //   body: JSON.stringify({
    //     amount: amountUSD,
    //     currency: "USDC",
    //     reference: `b2b_${userId}_${packageType}_${Date.now()}`,
    //     customer_email: "developer@example.com", // Get from clerk if needed
    //     redirect_url: `${appUrl}/developers`
    //   })
    // });
    // const data = await providerRes.json();
    // return NextResponse.json({ url: data.checkout_url });

    // MOCK URL FOR TESTING UI
    const mockCheckoutUrl = `https://checkout.your-crypto-provider.com/pay?amount=${amountUSD}&ref=b2b_${userId}_${packageType}`;
    return NextResponse.json({ url: mockCheckoutUrl });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
