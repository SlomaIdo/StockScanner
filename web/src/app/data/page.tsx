import type { Metadata } from "next";

import { DataOverview } from "./data-overview";

export const metadata: Metadata = { title: "Data · StockScanner" };

export default function DataPage() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight">Data</h1>
      <p className="mt-1 text-sm text-muted">
        What the pipeline has loaded, how fresh it is, and what looks suspicious.
      </p>
      <DataOverview />
    </main>
  );
}
