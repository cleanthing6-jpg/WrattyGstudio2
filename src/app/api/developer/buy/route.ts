import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

// Simple in-memory cache so we don't hit the rate API on every single click
let cachedRate: { value: number; timestamp: number } | null = null;
const CACHE_DURATION_MS = 1000 * 60 * 60; // Cache for 1 hour

async function getLiveUsdToNgnRate(): Promise<number> {
  const now = Date.now();
  
  // Return cached rate if it's less than 1 hour old
  if (cachedRate && (now - cachedRate.timestamp < CACHE_DURATION_MS)) {
    return cachedRate.value;
  }

  try {
    // Fetch free live rate (no API key required)
    const res = await fetch("https://open.er-api.com/v6/latest/USD", { cache: "no-store" });
    const data = await res.json();
    
    if (data.result === "success" && data.rates?.NGN) {
      const liveRate = data.rates.NGN;
      
      // Add a 5% buffer to protect against sudden market drops
      // This ensures you don't lose money if the Naira weakens
      const safeRate = Math.ceil(liveRate * 1.05);
      
      cachedRate = { value: safeRate, timestamp: now };
      return safeRate;
    }
  } catch (error) {
    console.error("Failed to fetch live exchange rate:", error);
  }

  // Fallback to a safe high rate if the API is completely down
  return 1600; 
}

export async function POST(req: Request) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const user = await currentUser();
    const email = user?.primaryEmailAddress?.emailAddress;
    if (!email) return NextResponse.json({ error: "No email found on your account." }, { status: 400 });

    const client = await getMongoClient();
    const db = client.db();
    const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });
    
    if (!profile) {
      return NextResponse.json({ error: "Please complete your company verification first." }, { status: 403 });
    }

    const body = await req.json();
    const packageType = body.packageType || "mix";

    // Fetch the live rate dynamically
    const usdToNgn = await getLiveUsdToNgnRate();

    let usdAmount = 0;
    let credits = 0;
    let usdAmount = 0;

    if (packageType === "master") {
      usdAmount = 1000;
      credits = 1000;
    } else if (packageType === "starter") {
      usdAmount = 50;
      credits = 20;
    } else if (packageType === "growth") {
      usdAmount = 250;
      credits = 100;
    } else {
      usdAmount = 2500;
      credits = 1000;
    }

    // Convert to NGN using the live rate + buffer
    const amountNGN = usdAmount * usdToNgn;
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
          packageType: packageType,
          exchangeRateUsed: usdToNgn // Saved for your records
        },
      }),
    });

    const data = await response.json();
    
    if (!data.status) {
      return NextResponse.json({ error: data.message || "Paystack rejected the transaction" }, { status: 500 });
    }

    return NextResponse.json({ url: data.data.authorization_url });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || "Internal Server Error" }, { status: 500 });
  }
}
