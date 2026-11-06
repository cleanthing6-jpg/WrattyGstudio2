import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import getMongoClient from "@/lib/mongodb";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { companyName, website } = await req.json();

  if (!companyName || !website) {
    return NextResponse.json({ error: "Company name and website are required" }, { status: 400 });
  }

  // Basic validation: Website must look like a URL
  if (!website.startsWith("http://") && !website.startsWith("https://")) {
    return NextResponse.json({ error: "Website must be a valid URL starting with http" }, { status: 400 });
  }

  const client = await getMongoClient();
  const db = client.db();

  // Save or update their developer profile
  await db.collection("developer_profiles").updateOne(
    { clerkUserId: userId },
    { 
      $set: { 
        companyName, 
        website, 
        verifiedAt: new Date() 
      } 
    },
    { upsert: true }
  );

  return NextResponse.json({ success: true });
}
