"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

export default function LayoutClient({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Check if we are on the developers page
  const isDevPage = pathname === "/developers";

  return (
    <>
      {/* HIDE NAVBAR ON DEVELOPERS PAGE */}
      {!isDevPage && (
        <nav className="fixed top-0 w-full bg-black/90 backdrop-blur-md border-b border-gray-800 z-50">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <Link
              href="/"
              className="text-xl font-black bg-gradient-to-r from-green-400 to-yellow-500 bg-clip-text text-transparent"
            >
              WraGstudio
            </Link>

            <div className="flex gap-4 items-center">
              <Link href="/dashboard" className="text-gray-400 hover:text-white text-sm">
                Dashboard
              </Link>
              <Link href="/studio" className="text-gray-400 hover:text-white text-sm">
                Studio
              </Link>
              <Link href="/master" className="text-gray-400 hover:text-white text-sm">
                Master
              </Link>
              <Link href="/pricing" className="text-gray-400 hover:text-white text-sm">
                Pricing
              </Link>
            </div>
          </div>
        </nav>
      )}

      {/* CONDITIONAL PADDING (Developers page has its own layout) */}
      <main className={isDevPage ? "" : "pt-16"}>
        {children}
      </main>
    </>
  );
}
