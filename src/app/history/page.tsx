"use client";

import { useUser } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import Link from "next/link";

type HistoryItem = {
  id: number | string;
  type: string;
  prompt: string | null;
  result_url: string;
};

type HistoryResponse = {
  items?: HistoryItem[];
};

export default function History() {
  const { user } = useUser();
  const [items, setItems] = useState<HistoryItem[]>([]);

  useEffect(() => {
    if (!user) return;

    fetch("/api/history")
      .then((response) => response.json() as Promise<HistoryResponse>)
      .then((data) => setItems(data.items ?? []))
      .catch(() => {});
  }, [user]);

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">Sign in first</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">History</h1>

      {items.length === 0 && (
        <p className="text-gray-400">
          No generations yet.{" "}
          <Link
            href="/studio?type=beat"
            className="text-green-400"
          >
            Create your first beat →
          </Link>
        </p>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          className="bg-gray-900 rounded-xl p-4 mb-3 flex items-center justify-between"
        >
          <div>
            <p className="text-sm text-gray-400 capitalize">{item.type}</p>
            <p className="text-white">{item.prompt}</p>
          </div>

          <a
            href={item.result_url}
            target="_blank"
            rel="noreferrer"
            className="text-green-400 hover:underline text-sm"
          >
            Open →
          </a>
        </div>
      ))}
    </div>
  );
}
