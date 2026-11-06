import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";
import crypto from "crypto";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ keys: [] });

  const client = await getMongoClient();
  const db = client.db();
  
  // 1. Check if they already have keys
  let keys = await db.collection("api_clients").find({ clerkUserId: userId }).toArray();

  // 2. If they have NO keys, generate a free test key instantly
  if (keys.length === 0) {
    const testKey = "wratty_test_sk_" + crypto.randomBytes(16).toString("hex");
    const newKeyDoc = {
      clerkUserId: userId,
      name: "Test Developer Key",
      apiKey: testKey,
      credits: 5, // 5 free test mixes
      isTest: true,
      createdAt: new Date()
    };
    await db.collection("api_clients").insertOne(newKeyDoc);
    keys = [newKeyDoc];
  }

  return NextResponse.json({ keys });
}
