import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { ObjectId } from "mongodb";
import { getMongoClient } from "@/lib/mongodb";
import { sql } from "@/lib/db";

export async function GET() {
  try {
    const { userId } = await auth();
    if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    const rows = await col.find({ userId }).sort({ createdAt: -1 }).toArray();

    // The dashboard list lives in Mongo, but FINISHED ENGINE RENDERS live in
    // Postgres (mix_jobs). Nothing ever copied them over, which is why they
    // never showed up here. Read them straight from the source instead of
    // double-writing: only full renders (max_seconds IS NULL - previews are
    // always 30s), not dismissed, with a URL.
    let jobs: any[] = [];
    try {
      jobs = (await sql`
        SELECT id, artist_name, song_title, url, result, loudness, preset, created_at
        FROM mix_jobs
        WHERE user_id = ${userId} AND status = 'done'
          AND max_seconds IS NULL AND hidden_at IS NULL
          AND COALESCE(url, '') <> ''
        ORDER BY created_at DESC LIMIT 100
      `) as any[];
    } catch (e) {
      console.error("[mixes] render list failed", e);
    }

    const parsed = (v: any) => {
      if (typeof v === "string") { try { return JSON.parse(v); } catch { return {}; } }
      return v || {};
    };
    const tagged = new Set(rows.map((r: any) => String(r.jobId || "")).filter(Boolean));

    const renderMixes = jobs
      .filter((j: any) => !tagged.has(String(j.id)))
      .map((j: any) => {
        const f = parsed(j.result).files || {};
        const a = String(j.artist_name || "").trim();
        const t = String(j.song_title || "").trim();
        return {
          id: "job:" + j.id,
          name: a && t ? a + " - " + t : t || a || "My mix",
          url: String(j.url || ""),
          mp3: String(f.mp3 || j.url || ""),
          flac: String(f.flac || ""),
          loudness: j.loudness || "",
          preset: j.preset || "",
          createdAt: j.created_at,
        };
      });

    return NextResponse.json({ mixes: [...renderMixes, ...rows.map((r: any) => ({ id: r._id.toString(), name: r.name, url: r.url, mp3: r.mp3 || r.url || "", flac: r.flac || "", createdAt: r.createdAt }))] });
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

    // Engine renders are listed from Postgres, so "dismiss" = hide, never
    // delete. The rendered file stays available.
    if (id.startsWith("job:")) {
      await sql`UPDATE mix_jobs SET hidden_at = NOW()
                WHERE id = ${id.slice(4)} AND user_id = ${userId}`;
      return NextResponse.json({ ok: true });
    }

    const client = await getMongoClient();
    const col = client.db("wrattyg").collection("mixes");
    await col.deleteOne({ _id: new ObjectId(id), userId });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: (e && e.message) || String(e) }, { status: 500 });
  }
}
