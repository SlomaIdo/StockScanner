"use client";

import { useEffect, useState } from "react";

import { api, type Exchange, type IngestRun, type QualityReport } from "@/lib/api";
import { DASH, formatDateTime } from "@/lib/format";

const STATUS_STYLE: Record<IngestRun["status"], string> = {
  success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  partial: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  failed: "bg-red-500/15 text-red-600 dark:text-red-400",
  running: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
};

export function DataOverview() {
  const [exchanges, setExchanges] = useState<Exchange[] | null>(null);
  const [runs, setRuns] = useState<IngestRun[] | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const fail = (e: unknown) => {
      if (!signal.aborted) setError(String(e));
    };
    api.exchanges(signal).then(setExchanges).catch(fail);
    api.runs(signal).then(setRuns).catch(fail);
    api.quality(signal).then(setQuality).catch(fail);
    return () => controller.abort();
  }, []);

  const tracked = exchanges?.filter((e) => e.securities > 0) ?? [];
  const totalStocks = tracked.reduce((n, e) => n + e.securities, 0);

  return (
    <div className="mt-6 grid gap-8">
      {error && <p className="text-sm text-red-500">Could not load data: {error}</p>}

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="font-medium">Coverage by exchange</h2>
          <span className="text-sm text-muted">
            {exchanges ? `${totalStocks.toLocaleString()} stocks on ${tracked.length} exchanges` : ""}
          </span>
        </div>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Exchange</th>
                <th className="px-4 py-2 font-medium">Country</th>
                <th className="px-4 py-2 font-medium">Currency</th>
                <th className="px-4 py-2 text-right font-medium">Stocks</th>
                <th className="px-4 py-2 text-right font-medium">Latest prices</th>
              </tr>
            </thead>
            <tbody>
              {tracked.map((e) => (
                <tr key={e.mic} className="border-b border-border last:border-0">
                  <td className="px-4 py-2">
                    {e.name} <span className="font-mono text-xs text-muted">{e.mic}</span>
                  </td>
                  <td className="px-4 py-2 text-muted">{e.country_code}</td>
                  <td className="px-4 py-2 text-muted">{e.currency_code}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{e.securities}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-muted">
                    {e.last_bar_date ?? "not loaded yet"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="font-medium">Data quality</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {quality?.checks.map((c) => (
            <div key={c.name} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{c.description}</span>
                <span
                  className={`ml-3 rounded px-2 py-0.5 text-xs tabular-nums ${
                    c.count === 0 ? STATUS_STYLE.success : STATUS_STYLE.partial
                  }`}
                >
                  {c.count.toLocaleString()}
                </span>
              </div>
              {c.samples.length > 0 && (
                <ul className="mt-2 space-y-0.5 font-mono text-xs text-muted">
                  {c.samples.slice(0, 4).map((s) => (
                    <li key={s} className="truncate">
                      {s}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {!quality && !error && <p className="text-sm text-muted">Running checks…</p>}
        </div>
      </section>

      <section>
        <h2 className="font-medium">Recent pipeline runs</h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Job</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Scope</th>
                <th className="px-4 py-2 text-right font-medium">OK / failed</th>
                <th className="px-4 py-2 text-right font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs?.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-border last:border-0"
                  title={r.message ?? ""}
                >
                  <td className="px-4 py-2 font-medium">{r.job}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLE[r.status]}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="max-w-[14rem] truncate px-4 py-2 text-muted">
                    {r.scope ?? DASH}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {r.items_ok} / {r.items_failed}
                  </td>
                  <td className="px-4 py-2 text-right text-muted">
                    {formatDateTime(r.started_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
