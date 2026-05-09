import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auto-Edit — AI Video Editor for Instagram Reels",
  description: "Paste any Instagram reel. We learn the style. You shoot, we edit.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" style={{ colorScheme: "light" }}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
