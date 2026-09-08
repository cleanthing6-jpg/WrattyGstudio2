import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;
if (!uri) {
  throw new Error("Missing MONGODB_URI env var");
}

const options = {};

let client: MongoClient;
let clientPromise: Promise<MongoClient>;

if (process.env.NODE_ENV === "development") {
  const g = global as typeof globalThis & { _mongoClientPromise?: Promise<MongoClient> };
  if (!g._mongoClientPromise) {
    client = new MongoClient(uri, options);
    g._mongoClientPromise = client.connect();
  }
  clientPromise = g._mongoClientPromise;
} else {
  client = new MongoClient(uri, options);
  clientPromise = client.connect();
}

export default clientPromise;
