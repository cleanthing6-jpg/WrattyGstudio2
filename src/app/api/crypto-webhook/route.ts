import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";
import { grantCredits } from "@/lib/credits";
import crypto from "crypto";

// Exact recursive sorting function from NOWPayments docs
function sortObject(obj: any): any {
  if (typeof obj !== "object" || obj === null) return obj;
  if (Array.isArray(obj)) return obj.map(sortObject);
  
  return Object.keys(obj)
    .sort()
    .reduce((result: any, key: string) => {
      result[key] = sortObject(obj[key]);
      return result;
    }, {});
}

export async function POST(req: Request) {
  try {
    const rawBody = await req.text();
    const signature = req.headers.get("x-nowpayments-sig");
    const ipnSecret = process.env.NOWPAYMENTS_IPN_SECRET;

    if (!signature || !ipnSecret) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const parsedBody = JSON.parse(rawBody);
    const sortedBody = sortObject(parsedBody);

    const hmac = crypto.createHmac("sha512", ipnSecret);
    hmac.update(JSON.stringify(sortedBody));
    const expectedSignature = hmac.digest("hex");

    if (signature !== expectedSignature) {
      return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
    }

    const { payment_status, order_id } = parsedBody;

    if (payment_status === "finished" || payment_status === "confirmed") {
      if (!order_id) return NextResponse.json({ received: true });

      // --- HANDLE B2C (Main App Users) ---
      if (order_id.startsWith("b2c_")) {
        // Format: b2c_${userId}_${tier}_${timestamp}
        const parts = order_id.split("_");
        const userId = parts[1];
        const tier = parts[2];

        await grantCredits(userId, tier);
        console.log(`[crypto-webhook] Granted B2C credits: ${tier} to user ${userId}`);
      }

      // --- HANDLE B2B (Developer API) ---
      else if (order_id.startsWith("b2b_")) {
        // Format: b2b_${userId}_${packageType}_${timestamp}
        const parts = order_id.split("_");
        const userId = parts[1];
        const packageType = parts[2];

        const client = await getMongoClient();
        const db = client.db();
        const creditsToAdd = 1000;

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
            name: "NOWPayments Purchaser",
            apiKey: apiKey,
            credits: creditsToAdd,
            createdAt: new Date()
          });
        }
        console.log(`[crypto-webhook] Granted B2B credits: ${creditsToAdd} to dev ${userId}`);
      }
    }

    return NextResponse.json({ received: true });
  } catch (error: any) {
    console.error("[crypto-webhook] Error:", error);
    return NextResponse.json({ error: "Webhook error" }, { status: 500 });
  }
}
