import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ keys: [] });

  const client = await getMongoClient();
  const db = client.db();
  
  // ONLY return keys that are linked to this user's account.
  // Do NOT generate a new key here.
  const keys = await db.collection("api_clients").find({ clerkUserId: userId }).toArray();

  return NextResponse.json({ keys });
}
