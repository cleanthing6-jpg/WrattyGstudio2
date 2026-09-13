import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { ObjectId } from "mongodb";
import { getMongoClient } from "@/lib/mongodb";

export async function GET() {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    const rows = await col.find({ userId }).sort({ createdAt: -1 }).toArray();
    return NextResponse.json({
      mixes: rows.map((r: any) => ({ id: r._id.toString(), name: r.name, url: r.url, createdAt: r.createdAt })),
    });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const body = await req.json();
    const name = typeof body.name === "string" ? body.name.trim().slice(0, 120) : "";
    const url = typeof body.url === "string" ? body.url.trim() : "";
    if (!name || !url) return NextResponse.json({ error: "Name and URL required" }, { status: 400 });
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    const res = await col.insertOne({ userId, name, url, createdAt: new Date() });
    return NextResponse.json({ id: res.insertedId.toString() });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const id = req.nextUrl.searchParams.get("id");
    if (!id) return NextResponse.json({ error: "Missing id" }, { status: 400 });
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    await col.deleteOne({ _id: new ObjectId(id), userId });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}
