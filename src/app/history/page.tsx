"use client";
import { useUser } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import Link from "next/link";
export default function History() {
  const { user } = useUser();
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { if (user) fetch("/api/history").then(r => r.json()).then(d => setItems(d.items || [])); }, [user]);
  if (!user) return <div className="min-h-screen flex items-center justify-center"><p className="text-gray-400">Sign in first</p></div>;
  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">History</h1>
      {items.length === 0 && <p className="text-gray-400">No generations yet. <Link href="/studio?type=beat" className="text-green-400">Create your first beat →</Link></p>}
      {items.map((item: any) => (
        <div key={item.id} className="bg-gray-900 rounded-xl p-4 mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-400 capitalize">{item.type}</p>
            <p className="text-white">{item.prompt}</p>
          </div>
          <a href={item.result_url} target="_blank" className="text-green-400 hover:underline text-sm">Open →</a>
        </div>
      ))}
    </div>
  );
}
