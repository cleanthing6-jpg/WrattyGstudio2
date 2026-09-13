import { MongoClient } from "mongodb";

let clientPromise: Promise<MongoClient> | null = null;

export function getMongoClient(): Promise<MongoClient> {
  const uri = process.env.MONGODB_URI;
  if (!uri) return Promise.reject(new Error("Missing MONGODB_URI env var"));

  if (process.env.NODE_ENV === "development") {
    const g = global as typeof globalThis & { _mongoClientPromise?: Promise<MongoClient> };
    if (!g._mongoClientPromise) {
      g._mongoClientPromise = new MongoClient(uri, { serverSelectionTimeoutMS: 8000 }).connect();
      g._mongoClientPromise.catch(() => {});
    }
    return g._mongoClientPromise;
  }

  if (!clientPromise) {
    clientPromise = new MongoClient(uri, { serverSelectionTimeoutMS: 8000 }).connect();
    clientPromise.catch(() => { clientPromise = null; }); // handled + allows retry
  }
  return clientPromise;
}

export default getMongoClient;
