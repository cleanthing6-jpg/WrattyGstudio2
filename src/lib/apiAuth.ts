import { getDb } from "@/lib/mongodb"; 

export async function validateApiKey(req: Request) {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return { error: "Missing or invalid Authorization header", status: 401 };
  }

  const apiKey = authHeader.split(" ")[1];
  const db = await getDb();
  
  const client = await db.collection("api_clients").findOne({ apiKey });
  
  if (!client) {
    return { error: "Invalid API Key", status: 401 };
  }

  if (client.credits <= 0) {
    return { error: "Insufficient credits. Please top up your account.", status: 402 };
  }

  return { client, status: 200 };
}

export async function deductCredit(apiKey: string) {
  const db = await getDb();
  await db.collection("api_clients").updateOne(
    { apiKey },
    { $inc: { credits: -1 } }
  );
}
