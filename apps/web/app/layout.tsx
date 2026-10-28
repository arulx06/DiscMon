import type { Metadata } from "next";

import { NavLink } from "@/components/NavLink";

import "./globals.css";

const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "DiscMon";

export const metadata: Metadata = {
  title: {
    default: `${appName} · Career intelligence`,
    template: `%s · ${appName}`,
  },
  description: "Private, evidence-first career opportunity radar.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="container header-inner">
            <NavLink href="/">
              <span className="brand">
                Disc<span>Mon</span>
              </span>
            </NavLink>
            <nav className="nav" aria-label="Primary">
              <NavLink href="/opportunities">Opportunities</NavLink>
              <NavLink href="/watchlist">Watchlist</NavLink>
              <NavLink href="/deadlines">Deadlines</NavLink>
              <NavLink href="/digests">Digests</NavLink>
              <NavLink href="/sources">Sources</NavLink>
              <NavLink href="/discover">Discover</NavLink>
              <NavLink href="/health">Health</NavLink>
              <NavLink href="/settings">Settings</NavLink>
            </nav>
          </div>
        </header>
        <main>
          <div className="container">{children}</div>
        </main>
        <footer>
          <div className="container">
            Private single-user system. Unknown eligibility is never treated as yes.
          </div>
        </footer>
      </body>
    </html>
  );
}
