import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import AccountModeGuard from "@/components/AccountModeGuard";

export const metadata: Metadata = {
  title: { default: "Chokher Alo — Eyewear & Prescription Lenses", template: "%s | Chokher Alo" },
  description: "Eyewear, sunglasses and prescription-compatible lenses for customers across West Bengal."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="page-shell"><Header/><main><AccountModeGuard>{children}</AccountModeGuard></main><Footer/></div></body></html>;
}
