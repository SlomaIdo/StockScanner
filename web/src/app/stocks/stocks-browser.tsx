"use client";

import { useEffect, useState } from "react";

import { api, type Exchange, type Sector, type SecurityPage } from "@/lib/api";
import { DASH, formatPrice, formatUsdCompact } from "@/lib/format";

const PAGE_SIZE = 50;

export function StocksBrowser() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [exchange, setExchange] = useState("");
  const [sector, setSector] = useState("");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<SecurityPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.exchanges(controller.signal), api.sectors(controller.signal)])
      .then(([ex, sec]) => {
        setExchanges(ex.filter((e) => e.securities > 0));
        setSectors(sec);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .securities(
        {
          q: debouncedQuery,
          exchange,
          sector,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        },
        controller.signal,
      )
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(String(e));
      });
    return () => controller.abort();
  }, [debouncedQuery, exchange, sector, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const selectClass =
    "rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/40";

  return (
    <div className="mt-6">
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="search"
          placeholder="Search symbol or company"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          className={`${selectClass} sm:flex-1`}
          aria-label="Search symbol or company"
        />
        <select
          value={exchange}
          onChange={(e) => {
            setExchange(e.target.value);
            setPage(0);
          }}
          className={selectClass}
          aria-label="Exchange"
        >
          <option value="">All exchanges</option>
          {exchanges.map((e) => (
            <option key={e.mic} value={e.mic}>
              {e.name} ({e.securities})
            </option>
          ))}
        </select>
        <select
          value={sector}
          onChange={(e) => {
            setSector(e.target.value);
            setPage(0);
          }}
          className={selectClass}
          aria-label="Sector"
        >
          <option value="">All sectors</option>
          {sectors.map((s) => (
            <option key={s.id} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="mt-4 text-sm text-red-500">Could not load stocks: {error}</p>}

      <div className="mt-4 overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr className="border-b border-border">
              <th className="px-4 py-2 font-medium">Symbol</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Exchange</th>
              <th className="px-4 py-2 font-medium">Sector</th>
              <th className="px-4 py-2 text-right font-medium">Price</th>
              <th className="px-4 py-2 text-right font-medium">Mkt cap</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((s) => (
              <tr key={s.id} className="border-b border-border last:border-0">
                <td className="px-4 py-2 font-mono font-medium">{s.symbol}</td>
                <td className="max-w-[18rem] truncate px-4 py-2" title={s.name}>
                  {s.name}
                  {s.primary_security_id !== null && (
                    <span
                      className="ml-2 rounded bg-border px-1.5 py-0.5 text-[10px] text-muted"
                      title="Dual listing: the company's most liquid listing is on another exchange"
                    >
                      dual
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-muted">{s.exchange_mic}</td>
                <td className="px-4 py-2 text-muted">{s.sector ?? DASH}</td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatPrice(s.price, s.currency_code)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatUsdCompact(s.market_cap_usd)}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted">
                  No stocks match these filters.
                </td>
              </tr>
            )}
            {!data && !error && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm text-muted">
        <span>{data ? `${data.total.toLocaleString()} stocks` : ""}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-md border border-border px-3 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="tabular-nums">
            {page + 1} / {pages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
            disabled={page + 1 >= pages}
            className="rounded-md border border-border px-3 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
