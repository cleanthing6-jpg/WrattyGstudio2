"use client";
import { SignInButton, useUser } from "@clerk/nextjs";
import Link from "next/link";
export default function Home() {
  const { user } = useUser();
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 text-center">
      <h1 className="text-6xl font-black bg-gradient-to-r from-green-400 to-yellow-500 bg-clip-text text-transparent">WrattyGstudio</h1>
      <p className="text-xl text-gray-300 my-4">Upload. Automix. Master. Release.</p>
      <p className="text-gray-500 mb-8 max-w-md">AI-powered African music creation suite.</p>
      {user ? <Link href="/dashboard" className="bg-green-500 text-black font-bold py-3 px-8 rounded-full">Dashboard</Link> : <SignInButton mode="modal"><button className="bg-green-500 text-black font-bold py-3 px-8 rounded-full">Get Started Free</button></SignInButton>}
    </main>
  );
}
