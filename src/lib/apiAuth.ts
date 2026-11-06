import getMongoClient from "@/lib/mongodb";

export async function validateApiKey(req: Request) {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return { error: "Missing or invalid Authorization header", status: 401 };
  }

  const apiKey = authHeader.split(" ")[1];
  
  try {
    const client = await getMongoClient();
    const db = client.db();
    
    const apiClient = await db.collection("api_clients").findOne({ apiKey });
    
    if (!apiClient) {
      return { error: "Invalid API Key", status: 401 };
    }

    if (apiClient.credits <= 0) {
      return { error: "Insufficient credits. Please top up your account.", status: 402 };
    }

    return { client: apiClient, status: 200 };
  } catch (error) {
    console.error("MongoDB connection failed:", error);
    return { error: "Internal server error", status: 500 };
  }
}

export async function deductCredit(apiKey: string) {
  try {
    const client = await getMongoClient();
    const db = client.db();
    await db.collection("api_clients").updateOne(
      { apiKey },
      { $inc: { credits: -1 } }
    );
  } catch (error) {
    console.error("Failed to deduct credit:", error);
  }
}
