import { NextResponse } from "next/server";
import crypto from "crypto";
import { grantCredits } from "@/lib/credits";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  try {
    const body = await req.text();
    const signature = req.headers.get("x-crypto-signature") || ""; // Change based on provider

    // 1. Verify Signature (IMPORTANT: Change hash based on your provider's docs)
    const expectedSignature = crypto
      .createHmac("sha256", process.env.CRYPTO_WEBHOOK_SECRET!)
      .update(body)
      .digest("hex");

    if (signature !== expectedSignature) {
      return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
    }

    const event = JSON.parse(body);

    // 2. Check if payment was successful
    if (event.status === "success" || event.event === "charge.success") {
      const { reference } = event.data;

      // 3. Parse the reference to know if it's B2B or B2C
      // Example B2C Ref: "b2c_user_123_pro_123456789"
      // Example B2B Ref: "b2b_user_123_mix_123456789"
      const parts = reference.split("_");
      const type = parts[0];
      const userId = parts[1];
      const packageOrTier = parts[2];

      if (type === "b2c") {
        // Grant User Credits
        await grantCredits(userId, packageOrTier);
        console.log(`[Crypto Webhook] Granted ${packageOrTier} to User ${userId}`);
      } 
      else if (type === "b2b") {
        // Grant API Credits
        const client = await getMongoClient();
        const db = client.db();
        const creditsToAdd = packageOrTier === "master" ? 1000 : 1000;
        
        // Find their existing key and top up, or create a new one
        const existing = await db.collection("api_clients").findOne({ clerkUserId: userId });
        if (existing) {
          await db.collection("api_clients").updateOne(
            { clerkUserId: userId },
            { $inc: { credits: creditsToAdd } }
          );
        } else {
          const apiKey = "wratty_live_sk_" + crypto.randomBytes(16).toString("hex");
          await db.collection("api_clients").insertOne({
            clerkUserId: userId,
            name: "Crypto Purchaser",
            apiKey: apiKey,
            credits: creditsToAdd,
            createdAt: new Date()
          });
        }
        console.log(`[Crypto Webhook] Granted ${creditsToAdd} API credits to ${userId}`);
      }
    }

    return NextResponse.json({ received: true });
  } catch (error: any) {
    console.error("Crypto Webhook Error:", error);
    return NextResponse.json({ error: "Webhook error" }, { status: 500 });
  }
}
