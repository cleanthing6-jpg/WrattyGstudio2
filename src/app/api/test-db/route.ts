import { NextResponse } from "next/server";
import { getMongoClient } from "@/lib/mongodb";

export async function GET() {
  try {
    const client = await getMongoClient();
    const db = client.db("wrattyg");
    const collections = await db.listCollections().toArray();
    return NextResponse.json({ status: "connected", collections: collections.map((c) => c.name) });
  } catch (e: any) {
    return NextResponse.json({ status: "error", error: (e && e.message) || String(e) }, { status: 500 });
  }
}
