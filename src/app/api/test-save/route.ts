import { NextResponse } from "next/server";
import clientPromise from "@/lib/mongodb";

export async function GET() {
  try {
    const client = await clientPromise;
    const db = client.db("wrattyg");
    const col = db.collection("mixes");
    const probe = await col.insertOne({ userId: "probe", name: "probe", url: "probe", createdAt: new Date() });
    await col.deleteOne({ _id: probe.insertedId });
    const dbs = await client.db().admin().listDatabases();
    return NextResponse.json({ writeOk: true, dbs: dbs.databases.map((d: any) => d.name) });
  } catch (e: any) {
    return NextResponse.json({ writeOk: false, error: (e && e.message) || String(e) }, { status: 500 });
  }
}
