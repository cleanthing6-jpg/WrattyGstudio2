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

  // Auto-prefix https:// if the user forgot it
  let formattedWebsite = website.trim();
  if (!formattedWebsite.startsWith("http://") && !formattedWebsite.startsWith("https://")) {
    formattedWebsite = "https://" + formattedWebsite;
  }

  const client = await getMongoClient();
  const db = client.db();

  // Save or update their developer profile
  await db.collection("developer_profiles").updateOne(
    { clerkUserId: userId },
    { 
      $set: { 
        companyName, 
        website: formattedWebsite, 
        verifiedAt: new Date() 
      } 
    },
    { upsert: true }
  );

  return NextResponse.json({ success: true });
}
