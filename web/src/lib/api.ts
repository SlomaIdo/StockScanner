export type HealthResponse = {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
};

/** Fetch backend health. Calls go through the Next.js /api proxy. */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch("/api/health", { signal, cache: "no-store" });
  if (!res.ok && res.status !== 503) {
    throw new Error(`Health check failed: HTTP ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}
