import type { Metadata } from "next";
import Link from "next/link";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Mystery Shopper Dashboard",
  description: "Static results dashboard for the Mystery Shopper agent eval matrix",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <nav className="topnav">
          <span className="brand">
            <span className="brand-mark">MS</span> Mystery Shopper
          </span>
          <Link href="/">Leaderboard</Link>
          <Link href="/runs">Runs</Link>
          <Link href="/compare">Compare</Link>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
