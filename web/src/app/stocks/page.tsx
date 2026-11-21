import type { Metadata } from "next";

import { StocksBrowser } from "./stocks-browser";

export const metadata: Metadata = { title: "Stocks · StockScanner" };

export default function StocksPage() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight">Stocks</h1>
      <p className="mt-1 text-sm text-muted">
        The tracked universe, largest first. Prices and market caps are from the latest daily
        snapshot.
      </p>
      <StocksBrowser />
    </main>
  );
}
