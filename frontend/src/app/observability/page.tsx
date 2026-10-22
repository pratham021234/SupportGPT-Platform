"use client";

import React, { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import type {
  SystemDiagnostics,
  TraceSummary,
  TraceDetail,
  FailureInvestigation,
  EvaluationRunRecord,
  EvaluationComparison,
  UsageSummary,
  UserOrganizationSummary,
} from "@/types/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  Activity,
  BarChart3,
  AlertOctagon,
  RefreshCw,
  Cpu,
  Database,
  Server,
  Layers,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Eye,
  Play,
  GitCompare,
  Building,
  Check,
} from "lucide-react";

export default function ObservabilityConsolePage() {
  // Tenant Context
  const [organizations, setOrganizations] = useState<UserOrganizationSummary[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");

  // Navigation Tabs
  const [activeTab, setActiveTab] = useState<"health" | "traces" | "investigations" | "evaluations" | "usage">("health");

  // Diagnostics State
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);

  // Traces State
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [tracesTotal, setTracesTotal] = useState(0);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [traceFilterOutcome, setTraceFilterOutcome] = useState<string>("");
  const [traceFilterOp, setTraceFilterOp] = useState<string>("");
  const [tracesLoading, setTracesLoading] = useState(false);

  // Failure Investigations State
  const [investigations, setInvestigations] = useState<FailureInvestigation[]>([]);
  const [investigationsTotal, setInvestigationsTotal] = useState(0);
  const [selectedInvestigation, setSelectedInvestigation] = useState<FailureInvestigation | null>(null);
  const [investigationFilterStatus, setInvestigationFilterStatus] = useState<string>("");
  const [investigationsLoading, setInvestigationsLoading] = useState(false);
  const [updatingInvestigation, setUpdatingInvestigation] = useState(false);
  const [newStatus, setNewStatus] = useState<string>("open");
  const [resolutionNotes, setResolutionNotes] = useState<string>("");

  // Evaluation Benchmarks State
  const [evaluations, setEvaluations] = useState<EvaluationRunRecord[]>([]);
  const [evaluationsLoading, setEvaluationsLoading] = useState(false);
  const [showRunEvalModal, setShowRunEvalModal] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [newEvalDatasetId, setNewEvalDatasetId] = useState("supportgpt-eval-v1");
  const [newEvalDatasetVersion, setNewEvalDatasetVersion] = useState("1.0.0");
  const [newEvalThreshold, setNewEvalThreshold] = useState("5.0");

  // Comparison State
  const [comparisonModal, setComparisonModal] = useState<{
    isOpen: boolean;
    currentRun: EvaluationRunRecord | null;
    baselineRunId: string;
    result: EvaluationComparison | null;
    loading: boolean;
  }>({
    isOpen: false,
    currentRun: null,
    baselineRunId: "",
    result: null,
    loading: false,
  });

  // Usage State
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);

  // Global UI feedback
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // 1. Initial Load: Organizations
  useEffect(() => {
    async function loadIdentity() {
      try {
        const userRes = await apiClient.getCurrentUser();
        if (userRes.organizations && userRes.organizations.length > 0) {
          setOrganizations(userRes.organizations);
          const firstOrg = userRes.organizations[0];
          if (firstOrg) {
            setSelectedOrgId(firstOrg.organization_id);
          }
        }
      } catch (err) {
        console.warn("Could not load organization context:", err);
      }
    }
    loadIdentity();
  }, []);

  // 2. Tab Change and Data Fetching
  useEffect(() => {
    if (!selectedOrgId) return;
    setErrorMsg(null);
    setSuccessMsg(null);

    if (activeTab === "health") {
      fetchDiagnostics();
    } else if (activeTab === "traces") {
      fetchTraces();
    } else if (activeTab === "investigations") {
      fetchInvestigations();
    } else if (activeTab === "evaluations") {
      fetchEvaluations();
    } else if (activeTab === "usage") {
      fetchUsage();
    }
  }, [selectedOrgId, activeTab, traceFilterOutcome, traceFilterOp, investigationFilterStatus]);

  // Fetch Helpers
  const fetchDiagnostics = async () => {
    if (!selectedOrgId) return;
    try {
      setDiagLoading(true);
      const res = await apiClient.getDiagnostics(selectedOrgId);
      setDiagnostics(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load system diagnostics.");
    } finally {
      setDiagLoading(false);
    }
  };

  const fetchTraces = async () => {
    if (!selectedOrgId) return;
    try {
      setTracesLoading(true);
      const res = await apiClient.listTraces(selectedOrgId, {
        outcome: traceFilterOutcome || undefined,
        operation_type: traceFilterOp || undefined,
        limit: 50,
      });
      setTraces(res.items);
      setTracesTotal(res.total);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load execution traces.");
    } finally {
      setTracesLoading(false);
    }
  };

  const fetchInvestigations = async () => {
    if (!selectedOrgId) return;
    try {
      setInvestigationsLoading(true);
      const res = await apiClient.listInvestigations(selectedOrgId, {
        status: investigationFilterStatus || undefined,
        limit: 50,
      });
      setInvestigations(res.items);
      setInvestigationsTotal(res.total);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load failure investigations.");
    } finally {
      setInvestigationsLoading(false);
    }
  };

  const fetchEvaluations = async () => {
    if (!selectedOrgId) return;
    try {
      setEvaluationsLoading(true);
      const res = await apiClient.listEvaluations(selectedOrgId);
      setEvaluations(res.items);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load evaluation benchmark runs.");
    } finally {
      setEvaluationsLoading(false);
    }
  };

  const fetchUsage = async () => {
    if (!selectedOrgId) return;
    try {
      setUsageLoading(true);
      const res = await apiClient.getUsageSummary(selectedOrgId);
      setUsage(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load token usage and cost accounting.");
    } finally {
      setUsageLoading(false);
    }
  };

  const inspectTrace = async (traceId: string) => {
    if (!selectedOrgId) return;
    try {
      setErrorMsg(null);
      const detail = await apiClient.getTrace(selectedOrgId, traceId);
      setSelectedTrace(detail);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load trace detail.");
    }
  };

  const handleUpdateInvestigation = async () => {
    if (!selectedOrgId || !selectedInvestigation) return;
    try {
      setUpdatingInvestigation(true);
      setErrorMsg(null);
      const updated = await apiClient.updateInvestigation(selectedOrgId, selectedInvestigation.id, {
        status: newStatus,
        resolution_notes: resolutionNotes,
      });
      setSelectedInvestigation(updated);
      setSuccessMsg(`Investigation ${updated.fingerprint} updated successfully.`);
      fetchInvestigations();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to update investigation.");
    } finally {
      setUpdatingInvestigation(false);
    }
  };

  const handleCreateEvaluationRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrgId) return;
    try {
      setRunningEval(true);
      setErrorMsg(null);
      const newRun = await apiClient.createEvaluationRun(selectedOrgId, {
        dataset_id: newEvalDatasetId,
        dataset_version: newEvalDatasetVersion,
        regression_threshold_pct: parseFloat(newEvalThreshold) || 5.0,
      });
      setShowRunEvalModal(false);
      setSuccessMsg(`Evaluation benchmark run created: ${newRun.dataset_id} (Status: ${newRun.status}).`);
      fetchEvaluations();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to execute evaluation run.");
    } finally {
      setRunningEval(false);
    }
  };

  const handleCompareRuns = async () => {
    if (!selectedOrgId || !comparisonModal.currentRun || !comparisonModal.baselineRunId) return;
    try {
      setComparisonModal((prev) => ({ ...prev, loading: true }));
      const comparison = await apiClient.compareEvaluations(
        selectedOrgId,
        comparisonModal.currentRun.id,
        comparisonModal.baselineRunId
      );
      setComparisonModal((prev) => ({ ...prev, result: comparison, loading: false }));
    } catch (err: any) {
      setErrorMsg(err.message || "Comparison failed.");
      setComparisonModal((prev) => ({ ...prev, loading: false }));
    }
  };

  // Helper Badge Renderers
  const renderOutcomeBadge = (outcome: string) => {
    switch (outcome) {
      case "success":
        return <Badge variant="success">Success</Badge>;
      case "abstained":
        return <Badge variant="warning">Abstained</Badge>;
      case "blocked":
        return <Badge variant="danger">Policy Blocked</Badge>;
      case "failed":
        return <Badge variant="danger">Failed</Badge>;
      case "timed_out":
        return <Badge variant="warning">Timeout</Badge>;
      default:
        return <Badge variant="neutral">{outcome}</Badge>;
    }
  };

  const renderSeverityBadge = (severity: string) => {
    switch (severity) {
      case "critical":
        return <Badge variant="danger">Critical</Badge>;
      case "high":
        return <Badge variant="danger">High</Badge>;
      case "medium":
        return <Badge variant="warning">Medium</Badge>;
      case "low":
        return <Badge variant="neutral">Low</Badge>;
      default:
        return <Badge variant="neutral">{severity}</Badge>;
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "open":
        return <Badge variant="danger">Open</Badge>;
      case "investigating":
        return <Badge variant="warning">Investigating</Badge>;
      case "mitigated":
        return <Badge variant="info">Mitigated</Badge>;
      case "resolved":
        return <Badge variant="success">Resolved</Badge>;
      case "false_positive":
        return <Badge variant="neutral">False Positive</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  return (
    <div className="flex-1 bg-slate-950 text-slate-100 min-h-screen pl-64">
      {/* Top Header */}
      <header className="h-16 border-b border-slate-800 bg-slate-900/40 backdrop-blur px-8 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-indigo-400" />
          <h1 className="text-lg font-bold tracking-tight text-white">AI Observability & Reliability</h1>
          <Badge variant="success" className="text-xs">Phase 08 Active</Badge>
        </div>

        {/* Tenant Switcher */}
        <div className="flex items-center gap-3">
          <Building className="w-4 h-4 text-slate-400" />
          <select
            value={selectedOrgId}
            onChange={(e) => setSelectedOrgId(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {organizations.map((org) => (
              <option key={org.organization_id} value={org.organization_id}>
                {org.name} ({org.role})
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Main Container */}
      <main className="p-8 max-w-7xl mx-auto space-y-6">
        {/* Alerts */}
        {errorMsg && (
          <Alert variant="danger" className="mb-4">
            <AlertTriangle className="w-4 h-4 mr-2 inline" />
            {errorMsg}
          </Alert>
        )}
        {successMsg && (
          <Alert variant="success" className="mb-4">
            <CheckCircle2 className="w-4 h-4 mr-2 inline" />
            {successMsg}
          </Alert>
        )}

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 gap-6">
          <button
            onClick={() => setActiveTab("health")}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors ${
              activeTab === "health"
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Server className="w-4 h-4" />
            System Diagnostics
          </button>
          <button
            onClick={() => setActiveTab("traces")}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors ${
              activeTab === "traces"
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Layers className="w-4 h-4" />
            AI Execution Traces ({tracesTotal})
          </button>
          <button
            onClick={() => setActiveTab("investigations")}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors ${
              activeTab === "investigations"
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <AlertOctagon className="w-4 h-4" />
            Failure Investigations ({investigationsTotal})
          </button>
          <button
            onClick={() => setActiveTab("evaluations")}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors ${
              activeTab === "evaluations"
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Evaluation Benchmarks
          </button>
          <button
            onClick={() => setActiveTab("usage")}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 transition-colors ${
              activeTab === "usage"
                ? "border-b-2 border-indigo-500 text-indigo-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <DollarSign className="w-4 h-4" />
            Usage & Cost Accounting
          </button>
        </div>

        {/* TAB 1: SYSTEM DIAGNOSTICS */}
        {activeTab === "health" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-semibold text-white">Deep Reliability Diagnostics</h2>
                <p className="text-xs text-slate-400">
                  Non-blocking live probes of core platform dependencies, worker queues, and AI provider configurations.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchDiagnostics}
                disabled={diagLoading}
                className="flex items-center gap-2"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${diagLoading ? "animate-spin" : ""}`} />
                Run Diagnostics
              </Button>
            </div>

            {diagLoading && !diagnostics ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Skeleton className="h-32 rounded-xl" />
                <Skeleton className="h-32 rounded-xl" />
                <Skeleton className="h-32 rounded-xl" />
              </div>
            ) : diagnostics ? (
              <div className="space-y-6">
                {/* Status Bar */}
                <Card className="bg-slate-900/60 border-slate-800 p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-3 h-3 rounded-full ${
                        diagnostics.status === "healthy" ? "bg-emerald-500" : "bg-amber-500"
                      }`}
                    />
                    <div>
                      <div className="text-sm font-bold text-white capitalize">
                        Platform Status: {diagnostics.status}
                      </div>
                      <div className="text-xs text-slate-400">
                        {diagnostics.app_name} v{diagnostics.version} ({diagnostics.environment}) • Probed at{" "}
                        {new Date(diagnostics.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                  <Badge variant={diagnostics.status === "healthy" ? "success" : "warning"}>
                    {diagnostics.status.toUpperCase()}
                  </Badge>
                </Card>

                {/* Dependencies Grid */}
                <div>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                    Core Storage & Messaging Dependencies
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* PostgreSQL */}
                    <Card className="bg-slate-900/60 border-slate-800 p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Database className="w-4 h-4 text-indigo-400" />
                          <span className="text-sm font-semibold text-white">PostgreSQL 16 (RLS)</span>
                        </div>
                        <Badge
                          variant={diagnostics.dependencies.postgres.status === "up" ? "success" : "danger"}
                        >
                          {diagnostics.dependencies.postgres.status.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="text-xs text-slate-400">
                        Latency: <span className="text-slate-200 font-mono">{diagnostics.dependencies.postgres.latency_ms} ms</span>
                      </div>
                      {diagnostics.dependencies.postgres.error && (
                        <div className="text-xs text-rose-400 mt-2 truncate">
                          {diagnostics.dependencies.postgres.error}
                        </div>
                      )}
                    </Card>

                    {/* Redis */}
                    <Card className="bg-slate-900/60 border-slate-800 p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Server className="w-4 h-4 text-emerald-400" />
                          <span className="text-sm font-semibold text-white">Redis Queue / Cache</span>
                        </div>
                        <Badge
                          variant={diagnostics.dependencies.redis.status === "up" ? "success" : "warning"}
                        >
                          {diagnostics.dependencies.redis.status.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="text-xs text-slate-400">
                        Latency: <span className="text-slate-200 font-mono">{diagnostics.dependencies.redis.latency_ms} ms</span>
                      </div>
                      {diagnostics.dependencies.redis.error && (
                        <div className="text-xs text-amber-400 mt-2 truncate">
                          {diagnostics.dependencies.redis.error}
                        </div>
                      )}
                    </Card>

                    {/* Qdrant */}
                    <Card className="bg-slate-900/60 border-slate-800 p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Cpu className="w-4 h-4 text-violet-400" />
                          <span className="text-sm font-semibold text-white">Qdrant Vector Engine</span>
                        </div>
                        <Badge
                          variant={
                            diagnostics.dependencies.qdrant.status === "up"
                              ? "success"
                              : diagnostics.dependencies.qdrant.status === "degraded"
                              ? "warning"
                              : "danger"
                          }
                        >
                          {diagnostics.dependencies.qdrant.status.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="text-xs text-slate-400">
                        Latency: <span className="text-slate-200 font-mono">{diagnostics.dependencies.qdrant.latency_ms} ms</span>
                      </div>
                      {diagnostics.dependencies.qdrant.collections && (
                        <div className="text-[11px] text-slate-400 mt-1">
                          Collections: {diagnostics.dependencies.qdrant.collections.join(", ") || "None"}
                        </div>
                      )}
                    </Card>
                  </div>
                </div>

                {/* Workers and AI Providers */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Workers */}
                  <Card className="bg-slate-900/60 border-slate-800 p-5">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                      Durable Background Workers
                    </h3>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                        <div>
                          <div className="text-sm font-semibold text-white">Event Ingestion Worker</div>
                          <div className="text-xs text-slate-400">
                            Poll: {diagnostics.workers.ingestion_worker.poll_interval_seconds}s • Batch:{" "}
                            {diagnostics.workers.ingestion_worker.batch_size}
                          </div>
                        </div>
                        <Badge variant={diagnostics.workers.ingestion_worker.enabled ? "success" : "neutral"}>
                          {diagnostics.workers.ingestion_worker.enabled ? "RUNNING" : "DISABLED"}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-semibold text-white">Document Processing Worker</div>
                          <div className="text-xs text-slate-400">
                            Poll: {diagnostics.workers.document_worker.poll_interval_seconds}s • Batch:{" "}
                            {diagnostics.workers.document_worker.batch_size}
                          </div>
                        </div>
                        <Badge variant={diagnostics.workers.document_worker.enabled ? "success" : "neutral"}>
                          {diagnostics.workers.document_worker.enabled ? "RUNNING" : "DISABLED"}
                        </Badge>
                      </div>
                    </div>
                  </Card>

                  {/* AI Providers */}
                  <Card className="bg-slate-900/60 border-slate-800 p-5">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                      AI Model & Embedding Providers
                    </h3>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                        <div>
                          <div className="text-sm font-semibold text-white">Embedding Engine</div>
                          <div className="text-xs text-slate-400">
                            {diagnostics.ai_providers.embedding.provider} • {diagnostics.ai_providers.embedding.model} (
                            {diagnostics.ai_providers.embedding.dimensions} dim)
                          </div>
                        </div>
                        <Badge variant={diagnostics.ai_providers.embedding.status === "ready" ? "success" : "danger"}>
                          {diagnostics.ai_providers.embedding.status.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-semibold text-white">LLM Generation Provider</div>
                          <div className="text-xs text-slate-400">
                            {diagnostics.ai_providers.llm.provider} • {diagnostics.ai_providers.llm.model} (Tier:{" "}
                            {diagnostics.ai_providers.llm.pricing_tier})
                          </div>
                        </div>
                        <Badge variant="info">
                          {diagnostics.ai_providers.llm.status.toUpperCase()}
                        </Badge>
                      </div>
                    </div>
                  </Card>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-sm">No diagnostic data available.</div>
            )}
          </div>
        )}

        {/* TAB 2: AI EXECUTION TRACES */}
        {activeTab === "traces" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-semibold text-white">AI Operation Execution Traces</h2>
                <p className="text-xs text-slate-400">
                  Granular span timings, token consumption, correlation IDs, and policy decisions for every AI workflow.
                </p>
              </div>

              {/* Filters */}
              <div className="flex items-center gap-3">
                <select
                  value={traceFilterOutcome}
                  onChange={(e) => setTraceFilterOutcome(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-200"
                >
                  <option value="">All Outcomes</option>
                  <option value="success">Success</option>
                  <option value="abstained">Abstained</option>
                  <option value="blocked">Blocked</option>
                  <option value="failed">Failed</option>
                  <option value="timed_out">Timed Out</option>
                </select>
                <select
                  value={traceFilterOp}
                  onChange={(e) => setTraceFilterOp(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-200"
                >
                  <option value="">All Operations</option>
                  <option value="answer_generation">Answer Generation</option>
                  <option value="response_verification">Response Verification</option>
                  <option value="evidence_retrieval">Evidence Retrieval</option>
                  <option value="query_embedding">Query Embedding</option>
                  <option value="benchmark_evaluation">Benchmark Evaluation</option>
                </select>
                <Button variant="outline" size="sm" onClick={fetchTraces} disabled={tracesLoading}>
                  <RefreshCw className={`w-3.5 h-3.5 ${tracesLoading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </div>

            {/* Traces Table */}
            {tracesLoading && traces.length === 0 ? (
              <Skeleton className="h-64 rounded-xl" />
            ) : traces.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-slate-800 rounded-xl">
                <Layers className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <h3 className="text-sm font-semibold text-slate-300">No Execution Traces Recorded</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Traces are generated automatically when customer support questions, verification runs, or embeddings execute.
                </p>
              </div>
            ) : (
              <div className="border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
                    <tr>
                      <th className="px-4 py-3">Trace ID</th>
                      <th className="px-4 py-3">Operation</th>
                      <th className="px-4 py-3">Outcome</th>
                      <th className="px-4 py-3">Duration</th>
                      <th className="px-4 py-3">Evidence</th>
                      <th className="px-4 py-3">Tokens</th>
                      <th className="px-4 py-3">Est. Cost</th>
                      <th className="px-4 py-3">Timestamp</th>
                      <th className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
                    {traces.map((trace) => (
                      <tr key={trace.id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-3 font-mono text-indigo-400 font-medium">
                          {trace.trace_id.substring(0, 16)}...
                        </td>
                        <td className="px-4 py-3 font-medium text-slate-200">
                          {trace.operation_type.replace(/_/g, " ")}
                        </td>
                        <td className="px-4 py-3">{renderOutcomeBadge(trace.outcome)}</td>
                        <td className="px-4 py-3 font-mono text-slate-300">{trace.total_duration_ms} ms</td>
                        <td className="px-4 py-3 text-slate-400">{trace.retrieved_evidence_count} docs</td>
                        <td className="px-4 py-3 font-mono text-slate-300">{trace.total_tokens.toLocaleString()}</td>
                        <td className="px-4 py-3 font-mono text-emerald-400">
                          ${trace.estimated_cost_usd.toFixed(6)}
                        </td>
                        <td className="px-4 py-3 text-slate-400">
                          {new Date(trace.created_at).toLocaleTimeString()}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => inspectTrace(trace.trace_id)}
                            className="text-xs h-7 px-2"
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Trace Inspection Modal */}
            {selectedTrace && (
              <Card className="bg-slate-900/90 border-slate-700 p-6 mt-6">
                <div className="flex justify-between items-start border-b border-slate-800 pb-4 mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-bold text-white">Execution Trace Inspector</h3>
                      {renderOutcomeBadge(selectedTrace.outcome)}
                    </div>
                    <div className="text-xs text-indigo-400 font-mono mt-1">
                      ID: {selectedTrace.trace_id}
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedTrace(null)}>
                    Close
                  </Button>
                </div>

                {/* Metadata Row */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs mb-6">
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block mb-1">Duration</span>
                    <span className="font-mono text-slate-200 font-bold">{selectedTrace.total_duration_ms} ms</span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block mb-1">Total Tokens</span>
                    <span className="font-mono text-slate-200 font-bold">
                      {selectedTrace.total_tokens} (In: {selectedTrace.input_tokens}, Out: {selectedTrace.output_tokens})
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block mb-1">Est. Cost (USD)</span>
                    <span className="font-mono text-emerald-400 font-bold">
                      ${selectedTrace.estimated_cost_usd.toFixed(6)}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block mb-1">Pipeline / Policy</span>
                    <span className="text-slate-200 font-mono">
                      v{selectedTrace.pipeline_version} / v{selectedTrace.policy_version}
                    </span>
                  </div>
                </div>

                {/* Execution Spans Waterfall */}
                <div>
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                    Execution Spans Timeline
                  </h4>
                  {selectedTrace.spans && selectedTrace.spans.length > 0 ? (
                    <div className="space-y-2">
                      {selectedTrace.spans.map((span, idx) => (
                        <div
                          key={idx}
                          className="bg-slate-950 border border-slate-800 rounded-lg p-3 flex items-center justify-between"
                        >
                          <div className="flex items-center gap-3">
                            <span className="w-5 h-5 rounded-full bg-slate-800 flex items-center justify-center text-[10px] font-mono text-slate-400">
                              {idx + 1}
                            </span>
                            <div>
                              <div className="text-sm font-semibold text-white">{span.name}</div>
                              <div className="text-xs text-slate-500">Stage: {span.stage}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-4">
                            <Badge variant={span.outcome === "success" ? "success" : "danger"}>
                              {span.outcome}
                            </Badge>
                            <span className="font-mono text-xs text-slate-300 w-16 text-right">
                              {span.duration_ms} ms
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-slate-500">No spans recorded for this trace.</div>
                  )}
                </div>
              </Card>
            )}
          </div>
        )}

        {/* TAB 3: FAILURE INVESTIGATIONS */}
        {activeTab === "investigations" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-semibold text-white">AI Failure Investigations</h2>
                <p className="text-xs text-slate-400">
                  Deduplicated failure fingerprints, diagnostic hypotheses, and operator incident workflows.
                </p>
              </div>

              {/* Status Filter */}
              <div className="flex items-center gap-3">
                <select
                  value={investigationFilterStatus}
                  onChange={(e) => setInvestigationFilterStatus(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-200"
                >
                  <option value="">All Statuses</option>
                  <option value="open">Open</option>
                  <option value="investigating">Investigating</option>
                  <option value="mitigated">Mitigated</option>
                  <option value="resolved">Resolved</option>
                  <option value="false_positive">False Positive</option>
                </select>
                <Button variant="outline" size="sm" onClick={fetchInvestigations} disabled={investigationsLoading}>
                  <RefreshCw className={`w-3.5 h-3.5 ${investigationsLoading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </div>

            {/* Investigations List */}
            {investigationsLoading && investigations.length === 0 ? (
              <Skeleton className="h-64 rounded-xl" />
            ) : investigations.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-slate-800 rounded-xl">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                <h3 className="text-sm font-semibold text-slate-300">Zero Active Failure Investigations</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Failures are automatically classified and deduplicated into investigations when pipeline errors occur.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {investigations.map((inv) => (
                  <Card
                    key={inv.id}
                    onClick={() => {
                      setSelectedInvestigation(inv);
                      setNewStatus(inv.status);
                      setResolutionNotes(inv.resolution_notes || "");
                    }}
                    className={`bg-slate-900/60 border p-5 cursor-pointer transition-colors ${
                      selectedInvestigation?.id === inv.id
                        ? "border-indigo-500 bg-slate-900/90"
                        : "border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-bold text-indigo-400">{inv.fingerprint}</span>
                        {renderSeverityBadge(inv.severity)}
                      </div>
                      {renderStatusBadge(inv.status)}
                    </div>
                    <div className="text-sm font-semibold text-white mb-1">
                      {inv.failure_category.replace(/_/g, " ").toUpperCase()}
                    </div>
                    <p className="text-xs text-slate-400 line-clamp-2 mb-3 font-mono">
                      {inv.sanitized_error_summary}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-800 pt-3">
                      <span>Occurrences: <strong className="text-slate-300">{inv.occurrence_count}</strong></span>
                      <span>Last seen: {new Date(inv.last_seen_at).toLocaleTimeString()}</span>
                    </div>
                  </Card>
                ))}
              </div>
            )}

            {/* Selected Investigation Detail Panel */}
            {selectedInvestigation && (
              <Card className="bg-slate-900/95 border-slate-700 p-6 mt-6">
                <div className="flex justify-between items-start border-b border-slate-800 pb-4 mb-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-bold text-white">Investigation: {selectedInvestigation.fingerprint}</h3>
                      {renderSeverityBadge(selectedInvestigation.severity)}
                      {renderStatusBadge(selectedInvestigation.status)}
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      Category: {selectedInvestigation.failure_category} • Occurrences: {selectedInvestigation.occurrence_count}
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedInvestigation(null)}>
                    Close
                  </Button>
                </div>

                {/* Sanitized Error Summary */}
                <div className="mb-6">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                    Sanitized Error Summary (Credentials Redacted)
                  </h4>
                  <pre className="bg-slate-950 border border-slate-800 p-4 rounded-lg text-xs font-mono text-rose-300 whitespace-pre-wrap">
                    {selectedInvestigation.sanitized_error_summary}
                  </pre>
                </div>

                {/* Diagnostic Hypotheses */}
                <div className="mb-6">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                    Diagnostic Hypotheses & Remediation Recommendations
                  </h4>
                  {selectedInvestigation.diagnostic_hypotheses.map((hypo, idx) => (
                    <div key={idx} className="bg-slate-950 border border-slate-800 rounded-lg p-4 mb-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-bold text-indigo-400 capitalize">{hypo.category.replace(/_/g, " ")}</span>
                        <Badge variant={hypo.confidence === "high" ? "danger" : "warning"}>
                          {hypo.confidence.toUpperCase()} CONFIDENCE
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-200 mb-2">{hypo.hypothesis}</p>
                      <div className="text-[11px] text-emerald-400 font-mono bg-emerald-950/30 p-2 rounded border border-emerald-900/50">
                        Suggested Remediation: {hypo.suggested_remediation}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Operator Actions / Workflow Form */}
                <div className="border-t border-slate-800 pt-4">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                    Operator Status & Resolution Workflow
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Investigation Status</label>
                      <select
                        value={newStatus}
                        onChange={(e) => setNewStatus(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-3 py-2 text-slate-200"
                      >
                        <option value="open">Open</option>
                        <option value="investigating">Investigating</option>
                        <option value="mitigated">Mitigated</option>
                        <option value="resolved">Resolved</option>
                        <option value="false_positive">False Positive</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Resolution Notes</label>
                      <textarea
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        rows={2}
                        placeholder="Document remediation steps or findings..."
                        className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-3 py-2 text-slate-200"
                      />
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleUpdateInvestigation}
                    disabled={updatingInvestigation}
                    className="flex items-center gap-2"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Save Investigation Status
                  </Button>
                </div>
              </Card>
            )}
          </div>
        )}

        {/* TAB 4: EVALUATION BENCHMARKS */}
        {activeTab === "evaluations" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-semibold text-white">Evaluation Benchmarks & Regression Detection</h2>
                <p className="text-xs text-slate-400">
                  Versioned RAG evaluation runs calculating Recall@k, MRR, Citation Validity, and detecting regressions.
                </p>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setShowRunEvalModal(true)}
                className="flex items-center gap-2"
              >
                <Play className="w-3.5 h-3.5" />
                Run Benchmark Evaluation
              </Button>
            </div>

            {/* Evaluations Table */}
            {evaluationsLoading && evaluations.length === 0 ? (
              <Skeleton className="h-64 rounded-xl" />
            ) : evaluations.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-slate-800 rounded-xl">
                <BarChart3 className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <h3 className="text-sm font-semibold text-slate-300">No Evaluation Runs Executed</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Run standard benchmark datasets to measure retrieval recall, citation validity, and abstention behavior.
                </p>
              </div>
            ) : (
              <div className="border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/80 border-b border-slate-800 text-slate-400 uppercase font-semibold">
                    <tr>
                      <th className="px-4 py-3">Dataset</th>
                      <th className="px-4 py-3">Recall@k</th>
                      <th className="px-4 py-3">MRR</th>
                      <th className="px-4 py-3">Citation Validity</th>
                      <th className="px-4 py-3">Groundedness</th>
                      <th className="px-4 py-3">Abstention Acc.</th>
                      <th className="px-4 py-3">Regression</th>
                      <th className="px-4 py-3">Executed</th>
                      <th className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
                    {evaluations.map((run) => (
                      <tr key={run.id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-3">
                          <div className="font-semibold text-white">{run.dataset_id}</div>
                          <div className="text-[11px] text-slate-500">v{run.dataset_version} ({run.dataset_size} items)</div>
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-200">
                          {(run.recall_at_k * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-200">
                          {run.mean_reciprocal_rank.toFixed(3)}
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-200">
                          {(run.citation_validity_rate * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-200">
                          {(run.evidence_groundedness_rate * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3 font-mono font-medium text-slate-200">
                          {(run.abstention_accuracy * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-3">
                          {run.has_regression ? (
                            <Badge variant="danger">REGRESSION DETECTED</Badge>
                          ) : (
                            <Badge variant="success">PASSED</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-400">
                          {new Date(run.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              const otherRuns = evaluations.filter((r) => r.id !== run.id);
                              setComparisonModal({
                                isOpen: true,
                                currentRun: run,
                                baselineRunId: otherRuns.length > 0 && otherRuns[0] ? otherRuns[0].id : "",
                                result: null,
                                loading: false,
                              });
                            }}
                            className="text-xs h-7 px-2"
                          >
                            <GitCompare className="w-3.5 h-3.5 mr-1" />
                            Compare
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Run Benchmark Modal */}
            {showRunEvalModal && (
              <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
                <Card className="bg-slate-900 border-slate-700 max-w-md w-full p-6">
                  <h3 className="text-base font-bold text-white mb-4">Run Evaluation Benchmark</h3>
                  <form onSubmit={handleCreateEvaluationRun} className="space-y-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Dataset Identifier</label>
                      <input
                        type="text"
                        value={newEvalDatasetId}
                        onChange={(e) => setNewEvalDatasetId(e.target.value)}
                        required
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Dataset Version</label>
                      <input
                        type="text"
                        value={newEvalDatasetVersion}
                        onChange={(e) => setNewEvalDatasetVersion(e.target.value)}
                        required
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Regression Tolerance Threshold (%)</label>
                      <input
                        type="number"
                        step="0.5"
                        value={newEvalThreshold}
                        onChange={(e) => setNewEvalThreshold(e.target.value)}
                        required
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
                      />
                    </div>
                    <div className="flex justify-end gap-3 pt-3">
                      <Button variant="ghost" size="sm" type="button" onClick={() => setShowRunEvalModal(false)}>
                        Cancel
                      </Button>
                      <Button variant="primary" size="sm" type="submit" disabled={runningEval}>
                        {runningEval ? "Executing..." : "Execute Benchmark"}
                      </Button>
                    </div>
                  </form>
                </Card>
              </div>
            )}

            {/* Run Comparison Modal */}
            {comparisonModal.isOpen && comparisonModal.currentRun && (
              <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
                <Card className="bg-slate-900 border-slate-700 max-w-2xl w-full p-6">
                  <div className="flex justify-between items-center border-b border-slate-800 pb-3 mb-4">
                    <h3 className="text-base font-bold text-white">Compare Benchmark Runs</h3>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setComparisonModal((prev) => ({ ...prev, isOpen: false }))}
                    >
                      Close
                    </Button>
                  </div>

                  <div className="flex items-center gap-4 mb-4">
                    <div className="flex-1">
                      <label className="block text-xs text-slate-400 mb-1">Current Run</label>
                      <div className="text-xs font-mono bg-slate-950 p-2 rounded border border-slate-800 text-slate-200">
                        {comparisonModal.currentRun.dataset_id} (v{comparisonModal.currentRun.dataset_version})
                      </div>
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs text-slate-400 mb-1">Baseline Run to Compare Against</label>
                      <select
                        value={comparisonModal.baselineRunId}
                        onChange={(e) =>
                          setComparisonModal((prev) => ({ ...prev, baselineRunId: e.target.value }))
                        }
                        className="w-full bg-slate-950 border border-slate-800 text-xs rounded-lg px-3 py-2 text-slate-200"
                      >
                        {evaluations
                          .filter((r) => r.id !== comparisonModal.currentRun?.id)
                          .map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.dataset_id} v{r.dataset_version} ({new Date(r.created_at).toLocaleDateString()})
                            </option>
                          ))}
                      </select>
                    </div>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCompareRuns}
                    disabled={comparisonModal.loading || !comparisonModal.baselineRunId}
                    className="mb-4"
                  >
                    Compute Delta & Regression Analysis
                  </Button>

                  {comparisonModal.result && (
                    <div className="space-y-4 border-t border-slate-800 pt-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-400 uppercase">Comparison Outcome</span>
                        {comparisonModal.result.has_regression ? (
                          <Badge variant="danger">REGRESSION DETECTED</Badge>
                        ) : (
                          <Badge variant="success">HEALTHY (NO REGRESSION)</Badge>
                        )}
                      </div>

                      {comparisonModal.result.regression_findings.length > 0 && (
                        <div className="bg-rose-950/30 border border-rose-900/60 p-3 rounded-lg text-xs text-rose-300">
                          <strong className="block mb-1">Regression Alerts:</strong>
                          <ul className="list-disc pl-4 space-y-1">
                            {comparisonModal.result.regression_findings.map((f, i) => (
                              <li key={i}>{f}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                        {Object.entries(comparisonModal.result.deltas).map(([k, delta]) => (
                          <div key={k} className="bg-slate-950 p-3 rounded border border-slate-800">
                            <span className="text-slate-500 block capitalize mb-1">{k.replace(/_/g, " ")}</span>
                            <span
                              className={`font-mono font-bold ${
                                delta < -0.05 ? "text-rose-400" : delta >= 0 ? "text-emerald-400" : "text-slate-300"
                              }`}
                            >
                              {delta >= 0 ? "+" : ""}
                              {(delta * 100).toFixed(1)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: USAGE & COST ACCOUNTING */}
        {activeTab === "usage" && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-base font-semibold text-white">Token Usage & Cost Accounting</h2>
                <p className="text-xs text-slate-400">
                  Granular consumption by model tier and pipeline stage using documented, versioned pricing schedules.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={fetchUsage} disabled={usageLoading}>
                <RefreshCw className={`w-3.5 h-3.5 ${usageLoading ? "animate-spin" : ""}`} />
              </Button>
            </div>

            {usageLoading && !usage ? (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Skeleton className="h-28 rounded-xl" />
                <Skeleton className="h-28 rounded-xl" />
                <Skeleton className="h-28 rounded-xl" />
                <Skeleton className="h-28 rounded-xl" />
              </div>
            ) : usage ? (
              <div className="space-y-6">
                {/* Top Summary Cards */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <Card className="bg-slate-900/60 border-slate-800 p-4">
                    <span className="text-xs text-slate-400 block mb-1">Total Operations</span>
                    <div className="text-2xl font-bold font-mono text-white">
                      {usage.total_requests.toLocaleString()}
                    </div>
                    <span className="text-[11px] text-slate-500">Tracked AI requests</span>
                  </Card>
                  <Card className="bg-slate-900/60 border-slate-800 p-4">
                    <span className="text-xs text-slate-400 block mb-1">Total Tokens</span>
                    <div className="text-2xl font-bold font-mono text-indigo-400">
                      {usage.total_tokens.toLocaleString()}
                    </div>
                    <span className="text-[11px] text-slate-500">
                      In: {usage.total_input_tokens.toLocaleString()} • Out: {usage.total_output_tokens.toLocaleString()}
                    </span>
                  </Card>
                  <Card className="bg-slate-900/60 border-slate-800 p-4">
                    <span className="text-xs text-slate-400 block mb-1">Total Estimated Cost</span>
                    <div className="text-2xl font-bold font-mono text-emerald-400">
                      ${usage.total_cost_usd.toFixed(4)}
                    </div>
                    <span className="text-[11px] text-slate-500">Documented model pricing</span>
                  </Card>
                  <Card className="bg-slate-900/60 border-slate-800 p-4">
                    <span className="text-xs text-slate-400 block mb-1">Usage Attribution</span>
                    <div className="text-sm font-semibold text-white mt-1">
                      {usage.actual_reported_tokens > 0 ? (
                        <Badge variant="success">Provider Reported</Badge>
                      ) : (
                        <Badge variant="neutral">Calculated / Inferred</Badge>
                      )}
                    </div>
                    <span className="text-[11px] text-slate-500 block mt-2">
                      Reported: {usage.actual_reported_tokens.toLocaleString()} tok
                    </span>
                  </Card>
                </div>

                {/* Model Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Card className="bg-slate-900/60 border-slate-800 p-5">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                      Breakdown by Model Tier
                    </h3>
                    {Object.keys(usage.by_model).length === 0 ? (
                      <div className="text-xs text-slate-500 py-6 text-center">No model usage recorded.</div>
                    ) : (
                      <div className="space-y-3">
                        {Object.entries(usage.by_model).map(([model, stats]) => (
                          <div
                            key={model}
                            className="flex items-center justify-between border-b border-slate-800/60 pb-2 text-xs"
                          >
                            <div>
                              <div className="font-semibold text-white">{model}</div>
                              <div className="text-slate-500">
                                {stats.requests} reqs • {stats.total_tokens.toLocaleString()} tokens
                              </div>
                            </div>
                            <span className="font-mono text-emerald-400 font-bold">
                              ${stats.cost_usd.toFixed(6)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>

                  {/* Operation Breakdown */}
                  <Card className="bg-slate-900/60 border-slate-800 p-5">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                      Breakdown by Operation Type
                    </h3>
                    {Object.keys(usage.by_operation).length === 0 ? (
                      <div className="text-xs text-slate-500 py-6 text-center">No operation usage recorded.</div>
                    ) : (
                      <div className="space-y-3">
                        {Object.entries(usage.by_operation).map(([op, stats]) => (
                          <div
                            key={op}
                            className="flex items-center justify-between border-b border-slate-800/60 pb-2 text-xs"
                          >
                            <div>
                              <div className="font-semibold text-white capitalize">{op.replace(/_/g, " ")}</div>
                              <div className="text-slate-500">
                                {stats.requests} ops • {stats.total_tokens.toLocaleString()} tokens
                              </div>
                            </div>
                            <span className="font-mono text-emerald-400 font-bold">
                              ${stats.cost_usd.toFixed(6)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                </div>

                {/* Pricing Schedule Reference Alert */}
                <div className="bg-slate-900/40 border border-slate-800 p-4 rounded-xl text-xs text-slate-400">
                  <strong className="text-slate-200 block mb-1">Pricing Schedule Methodology:</strong>
                  Estimates follow authoritative catalog pricing: OpenAI GPT-4o ($5.00/1M input, $15.00/1M output),
                  GPT-4o-mini ($0.15/1M input, $0.60/1M output), text-embedding-3-small ($0.02/1M), and FastEmbed
                  BGE/Deterministic ($0.00 infrastructure baseline). Currency: USD.
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-sm">No usage data recorded for this organization.</div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
