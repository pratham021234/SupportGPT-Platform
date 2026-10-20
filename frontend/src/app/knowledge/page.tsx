"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient, ApiError } from "@/lib/api";
import type {
  CitationItem,
  KnowledgeAnswerResponse,
  KnowledgeBase,
  KnowledgeSearchResponse,
  UserOrganizationSummary,
} from "@/types/api";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  BookOpen,
  Search,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
  Clock,
  RefreshCw,
  SlidersHorizontal,
  FileText,
} from "lucide-react";

export default function KnowledgeSearchAndQAPage() {
  // Tenant & Organization Context
  const [organizations, setOrganizations] = useState<UserOrganizationSummary[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>(""); // empty = all KBs

  // Mode & Query State
  const [queryMode, setQueryMode] = useState<"answer" | "search">("answer");
  const [queryText, setQueryText] = useState("");
  const [topK, setTopK] = useState(5);
  const [minScore, setMinScore] = useState(0.45);
  const [enableHybrid, setEnableHybrid] = useState(true);
  const [showOptions, setShowOptions] = useState(false);

  // Results State
  const [loading, setLoading] = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [answerResult, setAnswerResult] = useState<KnowledgeAnswerResponse | null>(null);
  const [searchResult, setSearchResult] = useState<KnowledgeSearchResponse | null>(null);
  const [activeCitation, setActiveCitation] = useState<CitationItem | null>(null);

  // 1. Initial Load: Retrieve current user organizations
  useEffect(() => {
    async function loadUserContext() {
      try {
        setInitLoading(true);
        const userRes = await apiClient.getCurrentUser();
        if (userRes.organizations && userRes.organizations.length > 0) {
          setOrganizations(userRes.organizations);
          const firstOrg = userRes.organizations[0];
          if (firstOrg) {
            setSelectedOrgId(firstOrg.organization_id);
          }
        } else {
          setError("No active organization memberships found for this account.");
        }
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 401) {
          setError("UNAUTHENTICATED");
        } else {
          setError("Failed to load organization context from backend API.");
        }
      } finally {
        setInitLoading(false);
      }
    }
    loadUserContext();
  }, []);

  // 2. Load Knowledge Bases when selected organization changes
  useEffect(() => {
    if (!selectedOrgId) return;

    async function loadKBs() {
      try {
        const kbRes = await apiClient.listKnowledgeBases(selectedOrgId);
        const items = kbRes.items || [];
        setKnowledgeBases(items);
        if (items.length > 0 && items[0]) {
          setSelectedKbId(items[0].id);
        } else {
          setSelectedKbId("");
        }
      } catch (err) {
        console.error("Failed to list knowledge bases", err);
      }
    }
    loadKBs();
  }, [selectedOrgId]);

  // 3. Execute Search or Grounded Q&A
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!queryText.trim() || !selectedOrgId) return;

    setLoading(true);
    setError(null);
    setAnswerResult(null);
    setSearchResult(null);
    setActiveCitation(null);

    try {
      const targetKbId = selectedKbId || null;

      if (queryMode === "answer") {
        const res = await apiClient.askKnowledge(
          selectedOrgId,
          targetKbId,
          queryText.trim(),
          topK,
          minScore
        );
        setAnswerResult(res);
      } else {
        const res = await apiClient.searchKnowledge(
          selectedOrgId,
          targetKbId,
          queryText.trim(),
          topK,
          minScore
        );
        setSearchResult(res);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || `Query failed with status ${err.status}`);
      } else {
        setError("An unexpected error occurred during knowledge retrieval.");
      }
    } finally {
      setLoading(false);
    }
  }

  // Render citation tag within answer text
  function renderFormattedAnswer(text: string, citations: CitationItem[]) {
    const parts = text.split(/(\[citation:\d+\])/g);
    return parts.map((part, index) => {
      const match = part.match(/\[citation:(\d+)\]/);
      if (match && match[1]) {
        const num = parseInt(match[1], 10);
        const cit = citations.find((c) => c.citation_number === num);
        return (
          <button
            key={index}
            type="button"
            onClick={() => cit && setActiveCitation(cit)}
            className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs font-semibold rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/30 hover:border-indigo-400 transition-colors"
            title={cit ? `Source: ${cit.source_title}` : "Citation"}
          >
            [{num}]
          </button>
        );
      }
      return <span key={index}>{part}</span>;
    });
  }

  // Unauthenticated Guard
  if (error === "UNAUTHENTICATED") {
    return (
      <div className="max-w-xl mx-auto mt-16 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mx-auto text-indigo-400">
          <BookOpen className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-bold text-white">Authentication Required</h1>
        <p className="text-sm text-slate-400">
          You must be signed in with an authorized organization account to access enterprise
          knowledge bases and execute grounded retrieval.
        </p>
        <Link href="/login">
          <Button variant="primary">Sign In to SupportGPT</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="brand" size="sm">
              Phase 06 Active
            </Badge>
            <Badge variant="success" size="sm">
              Vector Grounded
            </Badge>
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">
            Knowledge Retrieval & Answering
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Hybrid semantic retrieval via Qdrant and factual answering with verified claim-level citations.
          </p>
        </div>

        {/* Tenant Scope Selector */}
        {organizations.length > 0 && (
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Tenant:
            </label>
            <select
              value={selectedOrgId}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              {organizations.map((org) => (
                <option key={org.organization_id} value={org.organization_id}>
                  {org.name} ({org.role})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Query Form Card */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Mode Selector Tabs */}
            <div className="flex items-center p-1 bg-slate-900 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setQueryMode("answer")}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                  queryMode === "answer"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                Grounded Q&A
              </button>
              <button
                type="button"
                onClick={() => setQueryMode("search")}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                  queryMode === "search"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                <Search className="w-3.5 h-3.5" />
                Evidence Search
              </button>
            </div>

            {/* Knowledge Base Collection Filter */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">Collection:</label>
              <select
                value={selectedKbId}
                onChange={(e) => setSelectedKbId(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">All Collections ({knowledgeBases.length})</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => setShowOptions(!showOptions)}
                className={`p-1.5 rounded-lg border text-xs transition-colors ${
                  showOptions
                    ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
                }`}
                title="Retrieval Parameters"
              >
                <SlidersHorizontal className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Advanced Retrieval Options Drawer */}
          {showOptions && (
            <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-lg grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Top-K Evidence Excerpts: {topK}</label>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={topK}
                  onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                  className="w-full accent-indigo-500"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">
                  Relevance Threshold: {Math.round(minScore * 100)}%
                </label>
                <input
                  type="range"
                  min="0.2"
                  max="0.8"
                  step="0.05"
                  value={minScore}
                  onChange={(e) => setMinScore(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500"
                />
              </div>
              <div className="flex items-center gap-2 pt-4">
                <input
                  type="checkbox"
                  id="hybridToggle"
                  checked={enableHybrid}
                  onChange={(e) => setEnableHybrid(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="hybridToggle" className="text-slate-300">
                  Enable Reciprocal Rank Fusion (Hybrid Lexical + Vector)
                </label>
              </div>
            </div>
          )}

          {/* Query Input Bar */}
          <form onSubmit={handleSubmit} className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder={
                  queryMode === "answer"
                    ? "Ask a question (e.g. 'What is the SLA target for Priority 1 Critical incidents?')..."
                    : "Enter keywords or semantic concepts to retrieve matching document chunks..."
                }
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-4 pr-10 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                disabled={loading}
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              disabled={loading || !queryText.trim()}
              className="px-6 flex items-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : queryMode === "answer" ? (
                <>
                  <Sparkles className="w-4 h-4" />
                  Ask
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  Search
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Error Alert */}
      {error && (
        <Alert variant="danger" title="Knowledge Engine Error">
          {error}
        </Alert>
      )}

      {/* Empty State when no collections exist */}
      {!initLoading && knowledgeBases.length === 0 && (
        <Card className="text-center py-12">
          <CardContent className="space-y-4">
            <BookOpen className="w-12 h-12 text-slate-600 mx-auto" />
            <h3 className="text-base font-semibold text-slate-200">No Knowledge Collections Available</h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Your organization does not have any active knowledge bases yet. Upload company documents
              (PDF, DOCX, Markdown, TXT) via the Knowledge API to begin vector indexing.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full rounded-xl" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Skeleton className="h-40 rounded-xl" />
            <Skeleton className="h-40 rounded-xl" />
          </div>
        </div>
      )}

      {/* Grounded Answer Presentation */}
      {answerResult && !loading && (
        <div className="space-y-6">
          {/* Answer Card */}
          <Card className={answerResult.abstention_status ? "border-amber-500/40" : "border-indigo-500/30"}>
            <CardHeader
              title={
                <div className="flex items-center gap-2">
                  {answerResult.abstention_status ? (
                    <Badge variant="warning" size="sm">
                      Abstained
                    </Badge>
                  ) : (
                    <Badge variant="brand" size="sm">
                      Grounded Answer
                    </Badge>
                  )}
                  {answerResult.model_name && (
                    <Badge variant="neutral" size="sm">
                      {answerResult.model_name}
                    </Badge>
                  )}
                </div>
              }
              action={
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{answerResult.total_latency_ms} ms</span>
                </div>
              }
            />
            <CardContent className="p-6 space-y-4">
              {answerResult.abstention_status ? (
                <div className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="text-sm font-semibold text-amber-300">
                      System Refused to Hallucinate ({answerResult.abstention_reason || "Insufficient Evidence"})
                    </h4>
                    <p className="text-xs text-amber-200/80 leading-relaxed">
                      {answerResult.answer}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-slate-100 text-sm leading-relaxed whitespace-pre-wrap font-normal">
                  {renderFormattedAnswer(answerResult.answer, answerResult.citations)}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Validated Citations Panel */}
          {answerResult.citations.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  Validated Citations ({answerResult.citations.length})
                </h3>
                <span className="text-xs text-slate-500">
                  Verified against authoritative PostgreSQL records
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {answerResult.citations.map((cit) => (
                  <div
                    key={cit.citation_number}
                    className={`p-4 rounded-xl border text-xs transition-all ${
                      activeCitation?.citation_number === cit.citation_number
                        ? "bg-indigo-950/40 border-indigo-400 shadow-lg shadow-indigo-500/10"
                        : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 font-bold rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                          [{cit.citation_number}]
                        </span>
                        <span className="font-semibold text-slate-200 truncate max-w-[200px]">
                          {cit.source_title}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-500 font-mono">
                        {Math.round(cit.retrieval_score * 100)}% match
                      </span>
                    </div>

                    {cit.section_title && (
                      <div className="text-[11px] text-indigo-400 font-medium mb-2">
                        § {cit.section_title}
                      </div>
                    )}

                    <p className="text-slate-300 leading-relaxed font-mono bg-slate-950/50 p-2.5 rounded border border-slate-800/80">
                      &quot;{cit.excerpt}&quot;
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Raw Evidence Search Results */}
      {searchResult && !loading && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <FileText className="w-4 h-4 text-indigo-400" />
              Retrieved Evidence Chunks ({searchResult.total_results})
            </h3>
            <span className="text-xs text-slate-400 flex items-center gap-1 font-mono">
              <Clock className="w-3.5 h-3.5" />
              {searchResult.retrieval_latency_ms} ms
            </span>
          </div>

          {searchResult.evidence.length === 0 ? (
            <Card className="text-center py-8">
              <CardContent>
                <p className="text-xs text-slate-400">
                  No matching chunks exceeded the minimum similarity threshold ({Math.round(minScore * 100)}%).
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {searchResult.evidence.map((ev) => (
                <div
                  key={ev.evidence_id}
                  className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral" size="sm">
                        Rank #{ev.retrieval_rank}
                      </Badge>
                      <span className="font-semibold text-slate-200">{ev.source_title}</span>
                      {ev.section_title && (
                        <span className="text-slate-400">• § {ev.section_title}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[11px] text-slate-400">
                      <span>Method: {ev.scoring_method}</span>
                      <span>Score: {ev.retrieval_score}</span>
                    </div>
                  </div>

                  <p className="text-slate-300 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 leading-relaxed font-mono">
                    {ev.relevant_excerpt}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
