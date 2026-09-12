import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;

let clientPromise: Promise<MongoClient>;

if (!uri) {
  // A missing env var must NOT crash the route at import time.
  const p = Promise.reject(new Error("Missing MONGODB_URI env var"));
  p.catch(() => {});
  clientPromise = p;
} else if (process.env.NODE_ENV === "development") {
  const g = global as typeof globalThis & { _mongoClientPromise?: Promise<MongoClient> };
  if (!g._mongoClientPromise) {
    g._mongoClientPromise = new MongoClient(uri, {}).connect();
  }
  clientPromise = g._mongoClientPromise;
} else {
  clientPromise = new MongoClient(uri, {}).connect();
}

export default clientPromise;
