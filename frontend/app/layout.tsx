export const dynamic = "force-dynamic";

import type { Metadata } from "next";
import { Playfair_Display } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Soulens — AI Video Editor for Instagram Reels",
  description: "Paste any Instagram reel. We learn the style. You shoot, we edit.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full ${playfair.variable}`} style={{ colorScheme: "light" }}>
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
