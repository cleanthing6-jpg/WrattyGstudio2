import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ profile: null });

  const client = await getMongoClient();
  const db = client.db();
  const profile = await db.collection("developer_profiles").findOne({ clerkUserId: userId });

  return NextResponse.json({ profile });
}
