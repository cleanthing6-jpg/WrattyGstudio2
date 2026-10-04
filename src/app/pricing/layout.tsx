import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Pricing | WrattyGstudio",
  description:
    "Mix and mastering plans and prices - Single, EP and Album packs in Naira and USD.",
};

export default function PricingLayout({ children }: { children: ReactNode }) {
  return children;
}
