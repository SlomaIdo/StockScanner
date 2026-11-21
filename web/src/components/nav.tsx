"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/stocks", label: "Stocks" },
  { href: "/data", label: "Data" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-border">
      <nav className="mx-auto flex w-full max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
        <Link href="/" className="font-semibold tracking-tight">
          StockScanner
        </Link>
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`text-sm ${
              pathname.startsWith(l.href) ? "text-foreground" : "text-muted hover:text-foreground"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
