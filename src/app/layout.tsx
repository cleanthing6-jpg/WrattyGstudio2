import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "WrattyGstudio",
  description: "Upload. Automix. Master. Release.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-black text-white min-h-screen">
          <nav className="fixed top-0 w-full bg-black/90 backdrop-blur-md border-b border-gray-800 z-50">
            <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
              <a href="/" className="text-xl font-black bg-gradient-to-r from-green-400 to-yellow-500 bg-clip-text text-transparent">
                WrattyGstudio
              </a>
              <div className="flex gap-4 items-center">
                <a href="/dashboard" className="text-gray-400 hover:text-white text-sm">Dashboard</a>
                <a href="/studio" className="text-gray-400 hover:text-white text-sm">Studio</a>
                <a href="/pricing" className="text-gray-400 hover:text-white text-sm">Pricing</a>
              </div>
            </div>
          </nav>
          <main className="pt-16">{children}</main>
        </body>
      </html>
    </ClerkProvider>
  );
}
