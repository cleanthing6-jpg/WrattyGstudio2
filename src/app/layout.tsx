import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import LayoutClient from "@/components/LayoutClient";
import "./globals.css";

export const metadata: Metadata = {
  title: "WraGstudio",
  description: "AI mixing and mastering for all genres, powered by the Idan engine. Upload your song, get a release-ready mix and master.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-black text-white min-h-screen">
          <LayoutClient>
            {children}
          </LayoutClient>
        </body>
      </html>
    </ClerkProvider>
  );
}
