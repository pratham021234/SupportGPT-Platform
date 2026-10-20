"use client";

import React, { useEffect, useState, useMemo } from "react";
import { apiClient, ApiError } from "@/lib/api";
import type {
  ResponseDraft,
  VerificationRun,
  PolicyRule,
  ApprovalRequest,
  VerificationAuditEvent,
  UserOrganizationSummary,
} from "@/types/api";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  ShieldCheck,
  CheckCircle,
  FileCode,
  History,
  AlertTriangle,
  Clock,
  RefreshCw,
  Plus,
  Send,
  Eye,
  Check,
  X,
  FileEdit,
  Info,
  Building,
  Lock,
} from "lucide-react";

export default function VerificationConsolePage() {
  // Context state
  const [organizations, setOrganizations] = useState<UserOrganizationSummary[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [currentUserId, setCurrentUserId] = useState<string>("");

  // Tabs
  const [activeTab, setActiveTab] = useState<"drafts" | "approvals" | "policies" | "audit">("drafts");

  // Data states
  const [drafts, setDrafts] = useState<ResponseDraft[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<ResponseDraft | null>(null);
  const [activeRun, setActiveRun] = useState<VerificationRun | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [policies, setPolicies] = useState<PolicyRule[]>([]);
  const [auditEvents, setAuditEvents] = useState<VerificationAuditEvent[]>([]);

  // UI / Loading states
  const [initLoading, setInitLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modals state
  const [showCreateDraftModal, setShowCreateDraftModal] = useState(false);
  const [showCreatePolicyModal, setShowCreatePolicyModal] = useState(false);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [decisionModal, setDecisionModal] = useState<{
    isOpen: boolean;
    approval: ApprovalRequest | null;
    action: "approve" | "reject" | "request_revision";
    reason: string;
  }>({
    isOpen: false,
    approval: null,
    action: "approve",
    reason: "",
  });

  // Draft Form State
  const [newDraftQuery, setNewDraftQuery] = useState("");
  const [newDraftText, setNewDraftText] = useState("");
  const [newDraftEvidenceTitle, setNewDraftEvidenceTitle] = useState("");
  const [newDraftEvidenceExcerpt, setNewDraftEvidenceExcerpt] = useState("");

  // Policy Form State
  const [newPolicyName, setNewPolicyName] = useState("");
  const [newPolicyDesc, setNewPolicyDesc] = useState("");
  const [newPolicyCategory, setNewPolicyCategory] = useState("prohibited_terms");
  const [newPolicySeverity, setNewPolicySeverity] = useState("high");
  const [newPolicyRuleType, setNewPolicyRuleType] = useState("keyword_prohibition");
  const [newPolicyProhibitedTerms, setNewPolicyProhibitedTerms] = useState("100% guaranteed, free forever");

  // Approval Submission State
  const [approvalRole, setApprovalRole] = useState("agent");
  const [separationOfDuties, setSeparationOfDuties] = useState(true);

  // 1. Initial Load: Load user organizations and identity
  useEffect(() => {
    async function loadIdentity() {
      try {
        setInitLoading(true);
        const userRes = await apiClient.getCurrentUser();
        setCurrentUserId(userRes.user.id);
        if (userRes.organizations && userRes.organizations.length > 0) {
          setOrganizations(userRes.organizations);
          const firstOrg = userRes.organizations[0];
          if (firstOrg) {
            setSelectedOrgId(firstOrg.organization_id);
          }
        }
      } catch (err: unknown) {
        const msg = err instanceof ApiError ? err.message : "Failed to load user organization identity.";
        setError(msg);
      } finally {
        setInitLoading(false);
      }
    }
    loadIdentity();
  }, []);

  // 2. Fetch tenant-scoped verification data
  const fetchData = async () => {
    if (!selectedOrgId) return;
    try {
      setLoading(true);
      setError(null);

      const [draftsRes, approvalsRes, policiesRes, auditRes] = await Promise.all([
        apiClient.listDrafts(selectedOrgId),
        apiClient.listApprovals(selectedOrgId),
        apiClient.listPolicies(selectedOrgId),
        apiClient.listAuditTrail(selectedOrgId),
      ]);

      setDrafts(draftsRes.items || []);
      setApprovals(approvalsRes.items || []);
      setPolicies(policiesRes.items || []);
      setAuditEvents(auditRes.items || []);

      // If a draft is selected, keep it updated
      if (selectedDraft) {
        const refreshed = (draftsRes.items || []).find((d) => d.id === selectedDraft.id);
        if (refreshed) setSelectedDraft(refreshed);
      }
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to fetch verification resources.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedOrgId]);

  // Handle draft selection
  const handleSelectDraft = (draft: ResponseDraft) => {
    setSelectedDraft(draft);
    setActiveRun(null);
  };

  // Trigger verification pipeline on selected draft
  const handleVerifyDraft = async (draftId: string) => {
    if (!selectedOrgId) return;
    try {
      setVerifying(true);
      setError(null);
      setSuccessMsg(null);
      const run = await apiClient.verifyDraft(selectedOrgId, draftId);
      setActiveRun(run);
      setSuccessMsg(`Verification complete: Outcome '${run.status}' with risk '${run.risk_level}'.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Verification execution failed.";
      setError(msg);
    } finally {
      setVerifying(false);
    }
  };

  // Create Draft
  const handleCreateDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrgId || !newDraftQuery.trim() || !newDraftText.trim()) return;

    try {
      setLoading(true);
      const evidence = newDraftEvidenceExcerpt.trim()
        ? [
            {
              source_title: newDraftEvidenceTitle.trim() || "Authoritative Policy Document",
              excerpt: newDraftEvidenceExcerpt.trim(),
            },
          ]
        : [];

      const created = await apiClient.createDraft(selectedOrgId, {
        original_query: newDraftQuery.trim(),
        draft_text: newDraftText.trim(),
        evidence_references: evidence,
      });

      setShowCreateDraftModal(false);
      setNewDraftQuery("");
      setNewDraftText("");
      setNewDraftEvidenceTitle("");
      setNewDraftEvidenceExcerpt("");
      setSelectedDraft(created);
      setSuccessMsg(`Draft v1 created successfully.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to create draft candidate.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Submit Draft for Approval
  const handleSubmitForApproval = async () => {
    if (!selectedOrgId || !selectedDraft || !activeRun) return;

    try {
      setLoading(true);
      await apiClient.createApprovalRequest(selectedOrgId, selectedDraft.id, {
        draft_version: selectedDraft.version_number,
        verification_run_id: activeRun.id,
        required_role: approvalRole,
        separation_of_duties: separationOfDuties,
      });

      setShowApprovalModal(false);
      setSuccessMsg(`Draft v${selectedDraft.version_number} submitted to approval queue.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to submit for approval.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Submit Approval Decision (Approve / Reject / Revise)
  const handleCommitDecision = async () => {
    if (!selectedOrgId || !decisionModal.approval) return;

    try {
      setLoading(true);
      setError(null);
      await apiClient.decideApproval(selectedOrgId, decisionModal.approval.id, {
        decision: decisionModal.action,
        reason: decisionModal.reason.trim() || undefined,
      });

      setDecisionModal({ isOpen: false, approval: null, action: "approve", reason: "" });
      setSuccessMsg(`Decision '${decisionModal.action}' committed successfully.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to record approval decision.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Create Policy Rule
  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrgId || !newPolicyName.trim()) return;

    try {
      setLoading(true);
      const prohibitedList = newPolicyProhibitedTerms
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);

      await apiClient.createPolicy(selectedOrgId, {
        name: newPolicyName.trim(),
        description: newPolicyDesc.trim() || undefined,
        policy_category: newPolicyCategory,
        severity: newPolicySeverity,
        rule_type: newPolicyRuleType,
        rule_config: { prohibited_terms: prohibitedList, case_sensitive: false },
        is_enabled: true,
      });

      setShowCreatePolicyModal(false);
      setNewPolicyName("");
      setNewPolicyDesc("");
      setSuccessMsg(`Policy '${newPolicyName.trim()}' created and activated.`);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to create policy rule.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Toggle Policy
  const handleTogglePolicy = async (policyId: string) => {
    if (!selectedOrgId) return;
    try {
      await apiClient.togglePolicy(selectedOrgId, policyId);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to toggle policy status.";
      setError(msg);
    }
  };

  // Status Badge Helper
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "passed":
      case "approved":
      case "verified":
        return <Badge variant="success">{status.replace("_", " ")}</Badge>;
      case "passed_with_warnings":
      case "approval_pending":
      case "pending":
        return <Badge variant="warning">{status.replace("_", " ")}</Badge>;
      case "needs_revision":
      case "revision_required":
      case "revision_requested":
        return <Badge variant="brand">{status.replace("_", " ")}</Badge>;
      case "blocked":
      case "rejected":
      case "verification_failed":
        return <Badge variant="danger">{status.replace("_", " ")}</Badge>;
      case "invalidated":
      case "superseded":
        return <Badge variant="neutral">{status.replace("_", " ")}</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  // Support status badge
  const renderSupportBadge = (support: string) => {
    switch (support) {
      case "supported":
        return <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-400 border border-emerald-800/60 font-medium">Supported</span>;
      case "partially_supported":
        return <span className="text-xs px-2 py-0.5 rounded-full bg-amber-950/70 text-amber-400 border border-amber-800/60 font-medium">Partially Supported</span>;
      case "unsupported":
        return <span className="text-xs px-2 py-0.5 rounded-full bg-rose-950/70 text-rose-400 border border-rose-800/60 font-medium">Unsupported</span>;
      case "contradicted":
        return <span className="text-xs px-2 py-0.5 rounded-full bg-red-950/90 text-red-300 border border-red-700 font-bold">Contradicted</span>;
      default:
        return <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-medium">Unverifiable</span>;
    }
  };

  // Pending approval count
  const pendingApprovalsCount = useMemo(() => {
    return approvals.filter((a) => a.status === "pending").length;
  }, [approvals]);

  if (initLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Header & Tenant Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 shadow-sm shadow-indigo-950/50">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                Response Verification & Approval
                <Badge variant="success">Phase 07</Badge>
              </h1>
              <p className="text-sm text-slate-400">
                Deterministic Policy Enforcement, Traceable Evidence Grounding & Separation of Duties
              </p>
            </div>
          </div>
        </div>

        {/* Organization Switcher */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 shadow-inner">
            <Building className="w-4 h-4 text-slate-400" />
            <select
              value={selectedOrgId}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              className="bg-transparent text-sm text-slate-200 focus:outline-none cursor-pointer"
            >
              {organizations.map((org) => (
                <option key={org.organization_id} value={org.organization_id} className="bg-slate-900 text-white">
                  {org.name} ({org.role})
                </option>
              ))}
            </select>
          </div>
          <Button variant="outline" size="sm" onClick={fetchData} isLoading={loading}>
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <Alert variant="danger" title="Operation Error">
          {error}
        </Alert>
      )}
      {successMsg && (
        <Alert variant="success" title="Success">
          {successMsg}
        </Alert>
      )}

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800">
        <button
          onClick={() => setActiveTab("drafts")}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
            activeTab === "drafts"
              ? "border-indigo-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          Drafts & Verification
          <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
            {drafts.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("approvals")}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
            activeTab === "approvals"
              ? "border-indigo-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <CheckCircle className="w-4 h-4" />
          Human Approval Queue
          {pendingApprovalsCount > 0 && (
            <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-400 border border-amber-800/60 font-semibold animate-pulse">
              {pendingApprovalsCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("policies")}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
            activeTab === "policies"
              ? "border-indigo-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileCode className="w-4 h-4" />
          Policy Engine
          <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
            {policies.filter((p) => p.is_enabled).length} active
          </span>
        </button>

        <button
          onClick={() => setActiveTab("audit")}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all ${
            activeTab === "audit"
              ? "border-indigo-500 text-white"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <History className="w-4 h-4" />
          Append-Only Audit Trail
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: DRAFTS & CLAIM VERIFICATION */}
      {/* ========================================================================= */}
      {activeTab === "drafts" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Drafts List Column */}
          <div className="lg:col-span-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-white">Response Candidates</h2>
              <Button size="sm" onClick={() => setShowCreateDraftModal(true)}>
                <Plus className="w-4 h-4 mr-1" /> New Candidate
              </Button>
            </div>

            {drafts.length === 0 ? (
              <Card className="bg-slate-900/60 border-dashed border-slate-800 p-8 text-center">
                <FileEdit className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-sm text-slate-400">No response drafts found for this organization.</p>
                <Button size="sm" variant="outline" className="mt-4" onClick={() => setShowCreateDraftModal(true)}>
                  Create First Draft Candidate
                </Button>
              </Card>
            ) : (
              <div className="space-y-3">
                {drafts.map((d) => {
                  const isSelected = selectedDraft?.id === d.id;
                  return (
                    <div
                      key={d.id}
                      onClick={() => handleSelectDraft(d)}
                      className={`p-4 rounded-xl border transition-all cursor-pointer ${
                        isSelected
                          ? "bg-slate-900/90 border-indigo-500/60 ring-1 ring-indigo-500/20"
                          : "bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                            v{d.version_number}
                          </span>
                          {renderStatusBadge(d.lifecycle_status)}
                        </div>
                        <span className="text-[11px] text-slate-500">
                          {new Date(d.updated_at).toLocaleTimeString()}
                        </span>
                      </div>

                      <p className="text-sm font-medium text-slate-200 line-clamp-1 mb-1">
                        &quot;{d.original_query}&quot;
                      </p>
                      <p className="text-xs text-slate-400 line-clamp-2">{d.draft_text}</p>

                      <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                        <span>{d.evidence_references?.length || 0} evidence source(s)</span>
                        <span className="text-indigo-400 hover:underline flex items-center gap-1">
                          Inspect & Verify &rarr;
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Draft Detail & Verification Column */}
          <div className="lg:col-span-7">
            {selectedDraft ? (
              <div className="space-y-6">
                <Card className="bg-slate-900/60 border-slate-800">
                  <CardHeader className="flex flex-row items-center justify-between border-b border-slate-800 pb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-white">Draft Candidate Details</h3>
                        <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          v{selectedDraft.version_number}
                        </span>
                        {renderStatusBadge(selectedDraft.lifecycle_status)}
                      </div>
                      <p className="text-xs text-slate-400 mt-1">ID: {selectedDraft.id}</p>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleVerifyDraft(selectedDraft.id)}
                        isLoading={verifying}
                      >
                        <ShieldCheck className="w-4 h-4 mr-1.5" />
                        Run Verification Pipeline
                      </Button>
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-5 pt-5">
                    <div>
                      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                        Customer Inbound Query
                      </label>
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-sm text-slate-200">
                        {selectedDraft.original_query}
                      </div>
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                        Proposed Response Content
                      </label>
                      <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-sm text-slate-100 font-sans leading-relaxed whitespace-pre-wrap">
                        {selectedDraft.draft_text}
                      </div>
                    </div>

                    {/* Grounded Evidence Sources */}
                    <div>
                      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                        Attached Authoritative Evidence ({selectedDraft.evidence_references?.length || 0})
                      </label>
                      {selectedDraft.evidence_references?.length === 0 ? (
                        <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-900/40 text-xs text-amber-300 flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                          Zero evidence attached. Factual claims will be classified as unsupported.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {selectedDraft.evidence_references.map((ev, idx) => (
                            <div
                              key={idx}
                              className="p-3 rounded-lg bg-slate-950/40 border border-slate-800/80 text-xs space-y-1"
                            >
                              <div className="font-semibold text-indigo-300">
                                Source: {String(ev.source_title || "Enterprise Knowledge Base")}
                              </div>
                              <div className="text-slate-300 italic">&ldquo;{String(ev.excerpt || "")}&rdquo;</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Verification Findings Card */}
                {activeRun && (
                  <Card className="bg-slate-900/60 border-slate-800 animate-in fade-in duration-300">
                    <CardHeader className="flex flex-row items-center justify-between border-b border-slate-800 pb-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold text-white">Pipeline Verification Findings</h3>
                          {renderStatusBadge(activeRun.status)}
                          <Badge
                            variant={
                              activeRun.risk_level === "low"
                                ? "success"
                                : activeRun.risk_level === "medium"
                                ? "warning"
                                : "danger"
                            }
                          >
                            Risk: {activeRun.risk_level.toUpperCase()}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                          Pipeline {activeRun.verification_pipeline_version} &bull; Policy Set v{activeRun.policy_set_version} &bull; Latency: {activeRun.execution_time_ms}ms
                        </p>
                      </div>

                      {activeRun.status !== "blocked" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setShowApprovalModal(true)}
                        >
                          <Send className="w-4 h-4 mr-1.5" />
                          Submit for Approval
                        </Button>
                      )}
                    </CardHeader>

                    <CardContent className="space-y-4 pt-4">
                      {/* Diagnostic Summary */}
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-300">
                        <span className="font-semibold text-slate-400 mr-2">Diagnostic Summary:</span>
                        {String(activeRun.machine_readable_findings?.["disposition_summary"] || "Checks completed.")}
                      </div>

                      {/* Claim Findings Table */}
                      <div>
                        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Extracted Factual Claims ({activeRun.claim_findings?.length || 0})
                        </h4>
                        <div className="space-y-2">
                          {(activeRun.claim_findings || []).map((cf) => (
                            <div
                              key={cf.id}
                              className="p-3 rounded-lg bg-slate-950/40 border border-slate-800/80 space-y-1.5 text-xs"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <span className="font-medium text-slate-200">{cf.claim_text}</span>
                                {renderSupportBadge(cf.support_status)}
                              </div>
                              <div className="flex items-center gap-3 text-[11px] text-slate-400">
                                <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                                  Category: {cf.claim_category}
                                </span>
                                <span>Method: {cf.verification_method}</span>
                                {cf.confidence_score !== undefined && cf.confidence_score !== null && (
                                  <span>Confidence: {Math.round(cf.confidence_score * 100)}%</span>
                                )}
                              </div>
                              <p className="text-slate-400 italic text-[11px]">{cf.reason}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            ) : (
              <Card className="bg-slate-900/40 border-slate-800 p-12 text-center">
                <Eye className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <h3 className="text-base font-semibold text-slate-300">No Draft Selected</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Select a response candidate on the left to review its content, evidence bindings, and run verification.
                </p>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: HUMAN APPROVAL QUEUE */}
      {/* ========================================================================= */}
      {activeTab === "approvals" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-white">Pending Approval Queue</h2>
              <p className="text-xs text-slate-400">
                Independent reviews enforcing separation-of-duties and exact draft-version binding.
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={fetchData} isLoading={loading}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> Refresh Queue
            </Button>
          </div>

          {approvals.length === 0 ? (
            <Card className="bg-slate-900/60 border-dashed border-slate-800 p-12 text-center">
              <CheckCircle className="w-10 h-10 text-emerald-500/50 mx-auto mb-2" />
              <h3 className="text-base font-semibold text-slate-300">Approval Queue is Clear</h3>
              <p className="text-xs text-slate-500 mt-1">
                Zero response drafts currently pending human authorization.
              </p>
            </Card>
          ) : (
            <div className="space-y-3">
              {approvals.map((req) => {
                const parentDraft = drafts.find((d) => d.id === req.draft_id);
                const isStale = parentDraft && parentDraft.version_number !== req.draft_version;
                const isSelf = req.requested_by_user_id === currentUserId;

                return (
                  <Card
                    key={req.id}
                    className={`bg-slate-900/60 border ${
                      req.status === "pending" ? "border-amber-900/40" : "border-slate-800"
                    }`}
                  >
                    <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="space-y-2 max-w-2xl">
                        <div className="flex items-center gap-2.5">
                          <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                            Draft v{req.draft_version}
                          </span>
                          {renderStatusBadge(req.status)}
                          <Badge variant="neutral">Role: {req.required_role}</Badge>
                          {req.separation_of_duties && (
                            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-indigo-950/70 text-indigo-400 border border-indigo-800/60 font-medium">
                              <Lock className="w-3 h-3" /> Separation of Duties
                            </span>
                          )}
                        </div>

                        {parentDraft && (
                          <div className="space-y-1">
                            <p className="text-xs font-semibold text-slate-400">Query: {parentDraft.original_query}</p>
                            <p className="text-xs text-slate-300 italic line-clamp-2">&ldquo;{parentDraft.draft_text}&rdquo;</p>
                          </div>
                        )}

                        {isStale && (
                          <div className="text-xs text-rose-400 flex items-center gap-1 font-semibold">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Draft has been updated to v{parentDraft.version_number}. This approval request is invalidated.
                          </div>
                        )}

                        {isSelf && req.separation_of_duties && (
                          <div className="text-xs text-amber-400/90 flex items-center gap-1">
                            <Info className="w-3.5 h-3.5" />
                            You submitted this request. Server policy enforces independent review by another member.
                          </div>
                        )}

                        {req.decision_reason && (
                          <div className="text-xs text-slate-400">
                            <span className="font-semibold">Reviewer Note:</span> {req.decision_reason}
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      {req.status === "pending" && (
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="primary"
                            disabled={isStale || (isSelf && req.separation_of_duties)}
                            onClick={() =>
                              setDecisionModal({
                                isOpen: true,
                                approval: req,
                                action: "approve",
                                reason: "",
                              })
                            }
                          >
                            <Check className="w-4 h-4 mr-1" /> Approve
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setDecisionModal({
                                isOpen: true,
                                approval: req,
                                action: "request_revision",
                                reason: "",
                              })
                            }
                          >
                            <FileEdit className="w-4 h-4 mr-1" /> Revise
                          </Button>

                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() =>
                              setDecisionModal({
                                isOpen: true,
                                approval: req,
                                action: "reject",
                                reason: "",
                              })
                            }
                          >
                            <X className="w-4 h-4 mr-1" /> Reject
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: POLICY ENGINE */}
      {/* ========================================================================= */}
      {activeTab === "policies" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-white">Configured Organizational Policies</h2>
              <p className="text-xs text-slate-400">
                Auditable, versioned declarative rules enforced prior to human approval or delivery.
              </p>
            </div>
            <Button size="sm" onClick={() => setShowCreatePolicyModal(true)}>
              <Plus className="w-4 h-4 mr-1.5" /> Create Policy Rule
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {policies.map((pol) => (
              <Card key={pol.id} className="bg-slate-900/60 border-slate-800 flex flex-col justify-between">
                <CardHeader className="pb-3 border-b border-slate-800">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold text-white">{pol.name}</h3>
                      <p className="text-xs text-slate-400 mt-0.5">{pol.description || "Deterministic safety rule"}</p>
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                      v{pol.version_number}
                    </span>
                  </div>
                </CardHeader>

                <CardContent className="py-3 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Category:</span>
                    <Badge variant="neutral">{pol.policy_category}</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Severity:</span>
                    <Badge
                      variant={
                        pol.severity === "critical"
                          ? "danger"
                          : pol.severity === "high"
                          ? "warning"
                          : "neutral"
                      }
                    >
                      {pol.severity}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Rule Type:</span>
                    <span className="font-mono text-slate-300">{pol.rule_type}</span>
                  </div>

                  <div className="p-2 rounded bg-slate-950/60 border border-slate-800 text-[11px] text-slate-400 font-mono">
                    {JSON.stringify(pol.rule_config)}
                  </div>

                  <div className="pt-2 flex items-center justify-between border-t border-slate-800">
                    <span className="text-xs text-slate-400">Status:</span>
                    <Button
                      size="sm"
                      variant={pol.is_enabled ? "secondary" : "outline"}
                      onClick={() => handleTogglePolicy(pol.id)}
                    >
                      {pol.is_enabled ? "Enabled" : "Disabled"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: AUDIT TRAIL */}
      {/* ========================================================================= */}
      {activeTab === "audit" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-white">Append-Only Verification Audit Trail</h2>
              <p className="text-xs text-slate-400">
                Auditable event record of draft versions, pipeline evaluations, and human decisions.
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={fetchData} isLoading={loading}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> Refresh Trail
            </Button>
          </div>

          <Card className="bg-slate-900/60 border-slate-800">
            <CardContent className="p-0">
              <div className="divide-y divide-slate-800">
                {auditEvents.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-500">
                    Zero audit events recorded yet for this organization.
                  </div>
                ) : (
                  auditEvents.map((evt) => (
                    <div key={evt.id} className="p-4 flex items-start gap-3 hover:bg-slate-900/40 text-xs">
                      <div className="p-2 rounded-lg bg-slate-800 text-slate-300 mt-0.5">
                        <Clock className="w-3.5 h-3.5" />
                      </div>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-semibold text-indigo-300">{evt.event_type}</span>
                          <span className="text-[11px] text-slate-500">
                            {new Date(evt.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-slate-300">{evt.event_summary}</p>
                        <div className="text-[11px] text-slate-500 flex items-center gap-3">
                          <span>Entity: {evt.entity_type} ({evt.entity_id})</span>
                          <span>Actor: {evt.actor_id || "System"}</span>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: CREATE DRAFT CANDIDATE */}
      {/* ========================================================================= */}
      {showCreateDraftModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white">Create Response Draft Candidate</h3>
              <button
                onClick={() => setShowCreateDraftModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateDraft} className="space-y-4">
              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">Inbound Customer Query *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. What is your refund policy?"
                  value={newDraftQuery}
                  onChange={(e) => setNewDraftQuery(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">Proposed Response Text *</label>
                <textarea
                  required
                  rows={4}
                  placeholder="Draft reply content..."
                  value={newDraftText}
                  onChange={(e) => setNewDraftText(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 font-sans"
                />
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="text-xs font-semibold text-indigo-300 block">Grounding Evidence Source</span>
                <input
                  type="text"
                  placeholder="Source Title (e.g. Terms of Service, Refund Policy)"
                  value={newDraftEvidenceTitle}
                  onChange={(e) => setNewDraftEvidenceTitle(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                />
                <textarea
                  rows={2}
                  placeholder="Direct authoritative excerpt..."
                  value={newDraftEvidenceExcerpt}
                  onChange={(e) => setNewDraftEvidenceExcerpt(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500 font-sans"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button type="button" variant="outline" onClick={() => setShowCreateDraftModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" isLoading={loading}>
                  Save Draft Candidate
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: SUBMIT FOR APPROVAL */}
      {/* ========================================================================= */}
      {showApprovalModal && selectedDraft && activeRun && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white">Submit Draft for Human Approval</h3>
              <button onClick={() => setShowApprovalModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div className="text-slate-400">Target Draft:</div>
                <div className="text-slate-200 font-medium">v{selectedDraft.version_number} &bull; {selectedDraft.original_query}</div>
                <div className="text-indigo-400 text-[11px]">Run Verification ID: {activeRun.id}</div>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">Required Reviewer Role</label>
                <select
                  value={approvalRole}
                  onChange={(e) => setApprovalRole(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="agent">Agent (Peer Review)</option>
                  <option value="admin">Administrator (Escalated Review)</option>
                  <option value="owner">Organization Owner</option>
                </select>
              </div>

              <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-950 border border-slate-800">
                <input
                  type="checkbox"
                  id="sod"
                  checked={separationOfDuties}
                  onChange={(e) => setSeparationOfDuties(e.target.checked)}
                  className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0"
                />
                <label htmlFor="sod" className="text-xs text-slate-300 cursor-pointer">
                  Enforce Separation of Duties (requester cannot self-approve)
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button type="button" variant="outline" onClick={() => setShowApprovalModal(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSubmitForApproval} isLoading={loading}>
                  Submit to Approval Queue
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: COMMIT APPROVAL DECISION */}
      {/* ========================================================================= */}
      {decisionModal.isOpen && decisionModal.approval && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white capitalize">
                {decisionModal.action.replace("_", " ")} Draft Response
              </h3>
              <button
                onClick={() => setDecisionModal({ isOpen: false, approval: null, action: "approve", reason: "" })}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <p className="text-xs text-slate-300">
                Committing this decision will be permanently persisted in the tenant audit trail and bind to draft version {decisionModal.approval.draft_version}.
              </p>

              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">
                  Reason / Reviewer Notes {decisionModal.action !== "approve" && "*"}
                </label>
                <textarea
                  rows={3}
                  placeholder="Provide rationale for audit and revision tracking..."
                  value={decisionModal.reason}
                  onChange={(e) => setDecisionModal({ ...decisionModal, reason: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 font-sans"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDecisionModal({ isOpen: false, approval: null, action: "approve", reason: "" })}
                >
                  Cancel
                </Button>
                <Button
                  variant={decisionModal.action === "reject" ? "danger" : "primary"}
                  onClick={handleCommitDecision}
                  isLoading={loading}
                >
                  Confirm Decision
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: CREATE POLICY RULE */}
      {/* ========================================================================= */}
      {showCreatePolicyModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-semibold text-white">Create Policy Rule</h3>
              <button onClick={() => setShowCreatePolicyModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreatePolicy} className="space-y-4 text-xs">
              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">Rule Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Prohibited Commitment Phrases"
                  value={newPolicyName}
                  onChange={(e) => setNewPolicyName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-300 block mb-1">Category</label>
                  <select
                    value={newPolicyCategory}
                    onChange={(e) => setNewPolicyCategory(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="prohibited_terms">Prohibited Terms</option>
                    <option value="restricted_commitments">Restricted Commitments</option>
                    <option value="refund_compensation">Refund & Compensation</option>
                    <option value="factual_accuracy">Factual Accuracy</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-medium text-slate-300 block mb-1">Severity</label>
                  <select
                    value={newPolicySeverity}
                    onChange={(e) => setNewPolicySeverity(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical (Blocks)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">Rule Type</label>
                <select
                  value={newPolicyRuleType}
                  onChange={(e) => setNewPolicyRuleType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="keyword_prohibition">Keyword Prohibition</option>
                  <option value="required_phrase">Required Phrase / Disclaimer</option>
                  <option value="max_length">Maximum Length</option>
                  <option value="unsupported_claim_block">Unsupported Claim Block</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-slate-300 block mb-1">
                  Prohibited Phrases (Comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. 100% guaranteed, free forever"
                  value={newPolicyProhibitedTerms}
                  onChange={(e) => setNewPolicyProhibitedTerms(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 font-mono text-xs"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <Button type="button" variant="outline" onClick={() => setShowCreatePolicyModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" isLoading={loading}>
                  Create Policy
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
