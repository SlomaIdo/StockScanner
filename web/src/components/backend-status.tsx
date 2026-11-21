"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type State = "checking" | "ok" | "degraded" | "offline";

const LABELS: Record<State, string> = {
  checking: "Checking backend…",
  ok: "Backend and database online",
  degraded: "Backend online, database unavailable",
  offline: "Backend offline",
};

const DOT: Record<State, string> = {
  checking: "bg-gray-400",
  ok: "bg-emerald-500",
  degraded: "bg-amber-500",
  offline: "bg-red-500",
};

export function BackendStatus() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((h) => setState(h.status === "ok" ? "ok" : "degraded"))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          console.error(err);
          setState("offline");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span className={`h-2 w-2 rounded-full ${DOT[state]}`} aria-hidden />
      {LABELS[state]}
    </div>
  );
}
