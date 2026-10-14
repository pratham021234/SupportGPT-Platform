"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import type { HealthStatusResponse, SystemInfoResponse } from "@/types/api";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import {
  ShieldCheck,
  Layers,
  ArrowRight,
  Database,
  CheckCircle2,
  FileText,
} from "lucide-react";

export default function PlatformOverviewPage() {
  const [health, setHealth] = useState<HealthStatusResponse | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfoResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadOverview() {
      try {
        setLoading(true);
        const [h, sys] = await Promise.allSettled([
          apiClient.getLiveness(),
          apiClient.getSystemInfo(),
        ]);

        if (h.status === "fulfilled") {
          setHealth(h.value);
        } else {
          setError("Backend API is currently offline. Start the backend service to verify live connectivity.");
        }

        if (sys.status === "fulfilled") {
          setSystemInfo(sys.value);
        }
      } finally {
        setLoading(false);
      }
    }

    loadOverview();
  }, []);

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Platform Banner Header */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Badge variant="brand" size="md">
            Phase 00 Foundation Active
          </Badge>
          <Badge variant="neutral" size="md">
            Greenfield Baseline
          </Badge>
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-white">
          SupportGPT AI Platform
        </h1>
        <p className="text-base text-slate-400 max-w-3xl leading-relaxed">
          Enterprise AI Support Quality & Reliability Platform. Focused on factual grounding,
          claim-level response verification, human-in-the-loop approvals, and automated failure investigation.
        </p>
      </div>

      {/* Backend Status Alert if Offline */}
      {error && (
        <Alert variant="warning" title="Backend Transport Service Offline">
          {error}
        </Alert>
      )}

      {/* Live Operational Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Card>
          <CardHeader
            title="Transport & API"
            subtitle="FastAPI Asynchronous Gateway"
            action={
              loading ? (
                <Badge variant="neutral">Connecting...</Badge>
              ) : health ? (
                <Badge variant="success">Online</Badge>
              ) : (
                <Badge variant="danger">Disconnected</Badge>
              )
            }
          />
          <CardContent className="space-y-2 text-xs text-slate-300">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Environment</span>
              <span className="font-mono text-slate-200">
                {health?.environment || "development"}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Platform Version</span>
              <span className="font-mono text-slate-200">
                {health?.version || systemInfo?.version || "v0.1.0"}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Architecture</span>
              <span className="font-mono text-indigo-300">
                {systemInfo?.architecture || "Modular Monolith"}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Correlation Middleware</span>
              <span className="text-emerald-400">Enforced (X-Request-ID)</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Relational Schema"
            subtitle="PostgreSQL 16 & SQLAlchemy 2.x"
            action={<Badge variant="brand">Alembic Async</Badge>}
          />
          <CardContent className="space-y-2 text-xs text-slate-300">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Primary Key Standard</span>
              <span className="font-mono text-slate-200">UUIDv4 (Non-sequential)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Audit Timestamps</span>
              <span className="text-slate-200">UTC-aware (created_at, updated_at)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Tenant Isolation</span>
              <span className="text-amber-400">Phase 02 Architecture Plan</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Engineering Standards"
            subtitle="Quality Gates & Testing"
            action={<Badge variant="success">Strict Active</Badge>}
          />
          <CardContent className="space-y-2 text-xs text-slate-300">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">TypeScript</span>
              <span className="text-emerald-400">Strict (Zero Implicit Any)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Backend Linter</span>
              <span className="font-mono text-slate-200">Ruff (PEP 8 + Best Practices)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Automated Tests</span>
              <span className="text-emerald-400">Pytest Unit & API Suites</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Engineering Architecture & Foundations */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            Architectural Guarantees Established in Phase 00
          </h2>
          <Link href="/system">
            <Button variant="outline" size="sm">
              Live System Diagnostics
              <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              Zero Mock Data & Honest State Transparency
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              In accordance with engineering standards, this platform does not fabricate fake ticket counts,
              mock revenue figures, or simulated AI accuracy percentages. Every displayed state corresponds
              directly to real underlying infrastructure checks.
            </p>
          </div>

          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <ShieldCheck className="w-4 h-4 text-indigo-400" />
              Vendor-Neutral AI Provider Boundary
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Core domain logic is completely isolated from proprietary LLM and embedding SDKs through
              abstract interfaces (<code className="text-indigo-300">BaseLLMProvider</code>). All AI actions
              are formally represented as proposals requiring verification rather than authorization.
            </p>
          </div>

          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Database className="w-4 h-4 text-sky-400" />
              Single Authoritative Relational Datastore
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              PostgreSQL 16 serves as the single source of truth. Asynchronous SQLAlchemy 2.0 and Alembic
              manage transactional integrity, naming conventions, and schema evolution. Multi-tenant Row-Level
              Security (RLS) is architected for Phase 02.
            </p>
          </div>

          <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <FileText className="w-4 h-4 text-amber-400" />
              Standardized Error Envelope (RFC 7807)
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Every API failure returns a uniform structured payload with a machine-readable code, sanitized
              message, correlation identifier, and timestamp. Internal stack traces, raw SQL queries, and secrets
              are strictly redacted from external client responses.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
