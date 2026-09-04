"use client";
import { SignInButton, useUser } from "@clerk/nextjs";
import Link from "next/link";

export default function Home() {
  const { user } = useUser();
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 text-center">
      <div className="mb-8">
        <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-green-400 to-yellow-500 flex items-center justify-center">
          <svg className="w-10 h-10 text-black" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>
        </div>
        <h1 className="text-5xl md:text-7xl font-black mb-4 bg-gradient-to-r from-green-400 via-yellow-400 to-red-500 bg-clip-text text-transparent">
          WrattyGstudio
        </h1>
        <p className="text-xl text-gray-300 mb-2">Upload. Automix. Master. Release.</p>
        <p className="text-gray-500 max-w-md mx-auto">AI-powered African music creation suite. Generate beats, design covers, mix and master your tracks — all in one place.</p>
      </div>
      <div className="flex flex-col sm:flex-row gap-4">
        {user ? (
          <Link href="/dashboard" className="bg-green-500 hover:bg-green-400 text-black font-bold py-4 px-10 rounded-full text-lg transition">
            Open Studio →
          </Link>
        ) : (
          <SignInButton mode="modal">
            <button className="bg-green-500 hover:bg-green-400 text-black font-bold py-4 px-10 rounded-full text-lg transition">
              Get Started Free
            </button>
          </SignInButton>
        )}
        <Link href="/pricing" className="border border-gray-700 hover:border-gray-500 text-gray-300 font-bold py-4 px-10 rounded-full text-lg transition">
          View Pricing
        </Link>
      </div>
      <div className="mt-20 grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl w-full px-4">
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="text-3xl mb-3">🎵</div>
          <h3 className="font-bold mb-2">Beat Generation</h3>
          <p className="text-gray-500 text-sm">AI-generated African beats. Afrobeats, Amapiano, Highlife, and more.</p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="text-3xl mb-3">🎨</div>
          <h3 className="font-bold mb-2">Album Covers</h3>
          <p className="text-gray-500 text-sm">AI-generated artwork. Upload references, describe your vision.</p>
        </div>
        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
          <div className="text-3xl mb-3">🎛️</div>
          <h3 className="font-bold mb-2">Mix & Master</h3>
          <p className="text-gray-500 text-sm">Upload stems or rough recordings. AI automix and professional mastering.</p>
        </div>
      </div>
    </main>
  );
}
