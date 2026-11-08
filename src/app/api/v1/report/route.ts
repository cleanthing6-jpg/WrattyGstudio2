import { NextRequest, NextResponse } from "next/server";
import { sql } from "@/lib/db";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  // 1. Authenticate via API Key
  const authHeader = req.headers.get("authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Missing API key" }, { status: 401 });
  }
  
  const apiKey = authHeader.replace("Bearer ", "").trim();

  // 2. Find the user who owns this key
  const keyRows = (await sql`SELECT user_id FROM developer_keys WHERE api_key=${apiKey}`) as any[];
  const dev = keyRows[0];

  if (!dev) {
    return NextResponse.json({ error: "Invalid API key" }, { status: 401 });
  }

  // 3. Get the Job ID
  const id = req.nextUrl.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id required" }, { status: 400 });

  // 4. Fetch the result, ensuring they own the job
  const rows = (await sql`SELECT result FROM mix_jobs WHERE id=${id} AND user_id=${dev.user_id}`) as any[];
  const row = rows[0];

  if (!row || !row.result) {
    return NextResponse.json({ error: "Report not found" }, { status: 404 });
  }

  // Return the JSON telemetry
  return NextResponse.json(row.result);
}
