"use client";
export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      <h1 className="text-6xl font-bold mb-4 bg-gradient-to-r from-green-400 to-yellow-500 bg-clip-text text-transparent">WrattyGstudio2</h1>
      <p className="text-xl text-gray-400 mb-8">Upload. Automix. Master. Release.</p>
      <p className="text-gray-500 mb-8 max-w-md text-center">AI-powered African music creation suite.</p>
      <a href="/dashboard"><button className="bg-green-500 hover:bg-green-600 text-black font-bold py-3 px-8 rounded-full text-lg">Get Started Free</button></a>
    </main>
  );
}
