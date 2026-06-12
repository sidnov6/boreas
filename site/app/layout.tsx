import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "BOREAS — German power market agent, live track record",
  description:
    "Autonomous paper-trading agent for German day-ahead and imbalance power markets. Every thesis, every settlement, every playbook revision, published.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body
        className="min-h-[100dvh] antialiased"
        style={{ fontFamily: "var(--font-geist-sans), -apple-system, system-ui, sans-serif" }}
      >
        {children}
      </body>
    </html>
  );
}
