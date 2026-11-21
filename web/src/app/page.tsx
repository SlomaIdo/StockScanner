import { BackendStatus } from "@/components/backend-status";

const MODULES = [
  {
    title: "Screener",
    description: "Filter stocks worldwide by price, volume, technicals and fundamentals.",
  },
  {
    title: "Stock pages",
    description: "Charts, key stats, financial history and peers for any listing.",
  },
  {
    title: "Market structure",
    description: "Correlations and clusters across sectors and countries.",
  },
  {
    title: "ML & AI lab",
    description: "Backtests, models and an assistant that can run scans for you.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-12 sm:px-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">StockScanner</h1>
          <p className="mt-1 text-muted">Scan, browse and analyze stocks around the world.</p>
        </div>
        <BackendStatus />
      </header>

      <section className="mt-10 grid gap-4 sm:grid-cols-2">
        {MODULES.map((m) => (
          <div key={m.title} className="rounded-lg border border-border p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{m.title}</h2>
              <span className="text-xs text-muted">Coming soon</span>
            </div>
            <p className="mt-2 text-sm text-muted">{m.description}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
