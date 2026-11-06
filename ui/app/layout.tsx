import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mystery Shopper Dashboard",
  description: "Static results dashboard for the Mystery Shopper agent eval matrix",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav className="topnav">
          <Link href="/">Leaderboard</Link>
        </nav>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
