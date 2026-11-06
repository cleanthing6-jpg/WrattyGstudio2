import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import { findPlanById } from "@/lib/pricing";

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { tier } = await req.json();
    const plan = findPlanById(tier);
    
    if (!plan) return NextResponse.json({ error: "Invalid tier" }, { status: 400 });

    // Get the USD price from your pricing.ts
    const amountUSD = plan.usd;
    if (amountUSD === 0) return NextResponse.json({ error: "Free tier cannot be purchased" }, { status: 400 });

    const user = await currentUser();
    const email = user?.primaryEmailAddress?.emailAddress || "unknown@email.com";

    const appUrl = process.env.APP_URL || "https://wrattygstudio2.zevcloud.app";
    
    // --- REPLACE THIS SECTION WITH YOUR PROVIDER'S API ---
    // Example using a generic crypto provider API structure:
    
    // const providerRes = await fetch("https://api.stableflow.com/v1/payment-links", {
    //   method: "POST",
    //   headers: {
    //     "Authorization": `Bearer ${process.env.CRYPTO_API_KEY}`,
    //     "Content-Type": "application/json"
    //   },
    //   body: JSON.stringify({
    //     amount: amountUSD,
    //     currency: "USDC",
    //     reference: `b2c_${userId}_${tier}_${Date.now()}`,
    //     customer_email: email,
    //     redirect_url: `${appUrl}/dashboard?payment=success`
    //   })
    // });
    // const providerData = await providerRes.json();
    
    // For now, returning a mock URL so you can test the UI flow.
    // Replace this with the real URL from your provider.
    const mockCheckoutUrl = `https://checkout.your-crypto-provider.com/pay?amount=${amountUSD}&ref=b2c_${userId}_${tier}`;

    return NextResponse.json({ url: mockCheckoutUrl });

  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
