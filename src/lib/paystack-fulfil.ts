import getMongoClient from "@/lib/mongodb";
import { grantCredits } from "@/lib/credits";
import crypto from "crypto";

export async function fulfilPaystackReference(reference: string) {
  const secret = process.env.PAYSTACK_SECRET_KEY;
  if (!secret) throw new Error("No Paystack secret");

  // 1. Verify the transaction with Paystack
  const res = await fetch(`https://api.paystack.co/transaction/verify/${reference}`, {
    headers: { Authorization: `Bearer ${secret}` },
  });
  const data = await res.json();
  if (!data.status || data.data.status !== "success") return;

  const metadata = data.data.metadata;
  const client = await getMongoClient();
  const db = client.db();

  // --- IDEMPOTENCY CHECK ---
  const alreadyProcessed = await db.collection("processed_webhooks").findOne({ reference });
  if (alreadyProcessed) {
    console.log(`[paystack-fulfil] Reference ${reference} already processed. Ignoring.`);
    return;
  }

  // 2. Handle B2B API Purchases
  if (metadata?.type === "api_credits") {
    
    // Check if they already have a key
    const existing = await db.collection("api_clients").findOne({ clerkUserId: metadata.userId });
    if (existing) {
        // Top up existing
        await db.collection("api_clients").updateOne(
            { clerkUserId: metadata.userId },
            { $inc: { credits: metadata.credits } }
        );
    } else {
        // Generate brand new key
        const apiKey = "wratty_live_sk_" + crypto.randomBytes(16).toString("hex");
        await db.collection("api_clients").insertOne({
            clerkUserId: metadata.userId,
            name: "Developer Portal User",
            apiKey: apiKey,
            credits: metadata.credits,
            createdAt: new Date()
        });
    }
    return;
  }

  // 3. Handle B2C App Purchases (Your existing logic)
  if (metadata?.userId && metadata?.tier) {
    await grantCredits(metadata.userId, metadata.tier);
  }

  // --- MARK AS PROCESSED ---
  await db.collection("processed_webhooks").insertOne({ reference, date: new Date() });
}
