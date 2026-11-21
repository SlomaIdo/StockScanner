export type HealthResponse = {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
};

export type Exchange = {
  mic: string;
  name: string;
  country_code: string;
  timezone: string;
  currency_code: string;
  securities: number;
  last_bar_date: string | null;
};

export type Sector = { id: number; name: string; securities: number };

export type Security = {
  id: number;
  symbol: string;
  name: string;
  exchange_mic: string;
  currency_code: string;
  sector: string | null;
  price: number | null;
  market_cap_usd: number | null;
  snapshot_date: string | null;
  primary_security_id: number | null;
};

export type SecurityPage = { total: number; items: Security[] };

export type IngestRun = {
  id: number;
  job: string;
  scope: string | null;
  status: "running" | "success" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  items_ok: number;
  items_failed: number;
  message: string | null;
};

export type QualityReport = {
  generated_at: string;
  issues: number;
  checks: { name: string; description: string; count: number; samples: string[] }[];
};

/** GET a backend endpoint. Calls go through the Next.js /api proxy. */
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api${path}`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch("/api/health", { signal, cache: "no-store" });
  if (!res.ok && res.status !== 503) {
    throw new Error(`Health check failed: HTTP ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}

export const api = {
  exchanges: (signal?: AbortSignal) => get<Exchange[]>("/exchanges", signal),
  sectors: (signal?: AbortSignal) => get<Sector[]>("/sectors", signal),
  securities: (params: Record<string, string | number | undefined>, signal?: AbortSignal) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    return get<SecurityPage>(`/securities?${qs}`, signal);
  },
  runs: (signal?: AbortSignal) => get<IngestRun[]>("/ingest/runs?limit=15", signal),
  quality: (signal?: AbortSignal) => get<QualityReport>("/data/quality", signal),
};
