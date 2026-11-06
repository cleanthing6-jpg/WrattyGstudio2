import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";
import crypto from "crypto";
import { auth } from "@clerk/nextjs/server";

// Protect this route so only YOU can see the keys
async function isOwner() {
  const { userId } = await auth();
  return userId === process.env.OWNER_USER_ID;
}

export async function GET() {
  if (!(await isOwner())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const client = await getMongoClient();
    const db = client.db();
    const clients = await db.collection("api_clients").find().toArray();
    return NextResponse.json({ clients });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

export async function POST(req: Request) {
  if (!(await isOwner())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { name, credits } = await req.json();
    const apiKey = "wratty_live_sk_" + crypto.randomBytes(16).toString("hex");

    const client = await getMongoClient();
    const db = client.db();
    
    await db.collection("api_clients").insertOne({
      name,
      apiKey,
      credits: parseInt(credits) || 1000,
      createdAt: new Date()
    });

    return NextResponse.json({ success: true, apiKey });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
