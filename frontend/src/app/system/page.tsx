"use client";

import React, { useEffect, useState, useCallback } from "react";
import { apiClient } from "@/lib/api";
import type {
  HealthStatusResponse,
  ReadinessResponse,
} from "@/types/api";
import { HealthStatusCard } from "@/components/system/HealthStatusCard";
import { ServiceCheckTable } from "@/components/system/ServiceCheckTable";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  Activity,
  RefreshCw,
  Database,
} from "lucide-react";

export default function SystemDiagnosticsPage() {
  const [liveness, setLiveness] = useState<HealthStatusResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const fetchDiagnostics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [liveRes, readyRes] = await Promise.allSettled([
        apiClient.getLiveness(),
        apiClient.getReadiness(),
      ]);

      if (liveRes.status === "fulfilled") {
        setLiveness(liveRes.value);
      } else {
        setError(liveRes.reason?.message || "Failed to reach backend /healthz probe.");
      }

      if (readyRes.status === "fulfilled") {
        setReadiness(readyRes.value);
      } else if (readyRes.reason?.errorBody) {
        // Read structured readiness failure if returned
        setReadiness(readyRes.reason.errorBody as unknown as ReadinessResponse);
      }
      setLastRefreshed(new Date());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiagnostics();
  }, [fetchDiagnostics]);

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
            <Activity className="w-6 h-6 text-indigo-400" />
            System Diagnostics & Infrastructure Health
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time probes validating process liveness, authoritative database connectivity, and cache brokers.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {lastRefreshed && (
            <span className="text-xs text-slate-500 font-mono">
              Last probe: {lastRefreshed.toLocaleTimeString()}
            </span>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchDiagnostics}
            isLoading={loading}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Probe Now
          </Button>
        </div>
      </div>

      {/* Global Error Banner if Backend is down */}
      {error && (
        <Alert variant="danger" title="Backend Transport Unreachable">
          {error}. Ensure the FastAPI backend server is running on{" "}
          <code className="text-rose-200">http://localhost:8000</code>.
        </Alert>
      )}

      {/* Probes Summary Cards */}
      {loading && !liveness && !readiness ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <HealthStatusCard
            title="FastAPI Liveness"
            status={liveness ? "up" : "down"}
            description="Process liveness check verified via /healthz probe."
            errorMessage={!liveness ? "Process is not responding" : null}
          />

          <HealthStatusCard
            title="PostgreSQL Readiness"
            status={
              readiness?.dependencies?.["database"]?.status === "up"
                ? "up"
                : readiness?.dependencies?.["database"]?.status === "down"
                ? "down"
                : "degraded"
            }
            latencyMs={readiness?.dependencies?.["database"]?.latency_ms}
            description="Authoritative relational connection checked with query probe."
            errorMessage={readiness?.dependencies?.["database"]?.error}
          />

          <HealthStatusCard
            title="Redis Broker"
            status={
              readiness?.dependencies?.["redis"]?.status === "up"
                ? "up"
                : readiness?.dependencies?.["redis"]?.status === "degraded"
                ? "degraded"
                : "down"
            }
            latencyMs={readiness?.dependencies?.["redis"]?.latency_ms}
            description="Async queue broker for durable workflow execution."
            errorMessage={readiness?.dependencies?.["redis"]?.error}
          />
        </div>
      )}

      {/* Detailed Dependency Inspection Table */}
      <div className="space-y-3">
        <h2 className="text-base font-semibold text-slate-200 flex items-center gap-2">
          <Database className="w-4 h-4 text-indigo-400" />
          Service Dependency Probes (/readyz)
        </h2>
        {readiness?.dependencies ? (
          <ServiceCheckTable dependencies={readiness.dependencies} />
        ) : (
          <div className="p-6 text-center text-sm text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
            Awaiting readiness probe response...
          </div>
        )}
      </div>

      {/* Developer CLI Diagnostics Reference */}
      <Card>
        <CardHeader
          title="Manual CLI Diagnostic Commands"
          subtitle="Execute these Windows PowerShell or cURL commands to verify probe outputs directly"
        />
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-300">
              1. Liveness Probe (JSON response, HTTP 200)
            </span>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-indigo-300 overflow-x-auto flex items-center justify-between">
              <code>curl -i http://localhost:8000/healthz</code>
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-300">
              2. Readiness Probe (Dependency latency & connection health)
            </span>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-indigo-300 overflow-x-auto flex items-center justify-between">
              <code>curl -i http://localhost:8000/readyz</code>
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-300">
              3. System Information Metadata
            </span>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-indigo-300 overflow-x-auto flex items-center justify-between">
              <code>curl -i http://localhost:8000/api/v1/system/info</code>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
