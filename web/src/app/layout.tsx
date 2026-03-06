import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cascade — Research Intelligence",
  description:
    "AI-powered research assistant. Search papers, trace citation graphs, identify research gaps, and write academic text.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
