import { env } from "./env";
import type {
  HealthStatusResponse,
  ReadinessResponse,
  SystemInfoResponse,
  ErrorResponse,
  LoginResponse,
  LogoutResponse,
  CurrentUserResponse,
  UserOrganizationSummary,
  Ticket,
  TicketListResponse,
  TicketCreatePayload,
  TicketUpdatePayload,
  ConversationListResponse,
  Message,
  MessageListResponse,
  MessageCreatePayload,
  KnowledgeBaseListResponse,
  KnowledgeSearchResponse,
  KnowledgeAnswerResponse,
  ResponseDraft,
  VerificationRun,
  PolicyRule,
  ApprovalRequest,
  VerificationAuditEvent,
  SystemDiagnostics,
  TraceSummary,
  TraceDetail,
  FailureInvestigation,
  EvaluationRunRecord,
  EvaluationComparison,
  UsageSummary,
} from "../types/api";

export class ApiError extends Error {
  public status: number;
  public errorBody?: ErrorResponse;

  constructor(message: string, status: number, errorBody?: ErrorResponse) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorBody = errorBody;
  }
}

/**
 * Perform a typed HTTP fetch with timeout and structured error extraction.
 */
async function typedFetch<T>(
  endpoint: string,
  options: RequestInit = {},
  timeoutMs: number = 5000
): Promise<T> {
  const url = `${env.apiUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...options.headers,
      },
      signal: controller.signal,
      cache: "no-store",
      credentials: "include", // Transport HttpOnly cookies safely
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorBody: ErrorResponse | undefined;
      try {
        errorBody = await response.json();
      } catch {
        // Response was not JSON
      }
      const message =
        errorBody?.error?.message ||
        `HTTP Request failed with status ${response.status}: ${response.statusText}`;
      throw new ApiError(message, response.status, errorBody);
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof Error) {
      if (err.name === "AbortError") {
        throw new ApiError(`Request timeout after ${timeoutMs}ms`, 408);
      }
      throw new ApiError(err.message, 0);
    }
    throw new ApiError("An unknown network error occurred", 0);
  }
}

/**
 * Typed API Client for SupportGPT Backend Services
 */
export const apiClient = {
  /**
   * Probe backend process liveness (/healthz)
   */
  async getLiveness(): Promise<HealthStatusResponse> {
    return typedFetch<HealthStatusResponse>("/healthz");
  },

  /**
   * Probe platform dependency readiness (/readyz)
   */
  async getReadiness(): Promise<ReadinessResponse> {
    return typedFetch<ReadinessResponse>("/readyz");
  },

  /**
   * Fetch platform release and architecture metadata
   */
  async getSystemInfo(): Promise<SystemInfoResponse> {
    return typedFetch<SystemInfoResponse>("/api/v1/system/info");
  },

  /**
   * Authenticate user with password credentials (/api/v1/auth/login)
   */
  async login(credentials: { email: string; password: string }): Promise<LoginResponse> {
    return typedFetch<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
  },

  /**
   * Terminate active user session (/api/v1/auth/logout)
   */
  async logout(): Promise<LogoutResponse> {
    return typedFetch<LogoutResponse>("/api/v1/auth/logout", {
      method: "POST",
    });
  },

  /**
   * Retrieve active user identity profile (/api/v1/auth/me)
   */
  async getCurrentUser(): Promise<CurrentUserResponse> {
    return typedFetch<CurrentUserResponse>("/api/v1/auth/me");
  },

  /**
   * List organizations available to current user (/api/v1/organizations)
   */
  async getUserOrganizations(): Promise<UserOrganizationSummary[]> {
    return typedFetch<UserOrganizationSummary[]>("/api/v1/organizations");
  },

  /**
   * List tickets for an organization
   */
  async listTickets(
    orgId: string,
    params?: { status?: string; priority?: string; search?: string; limit?: number; offset?: number }
  ): Promise<TicketListResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.append("status", params.status);
    if (params?.priority) query.append("priority", params.priority);
    if (params?.search) query.append("search", params.search);
    if (params?.limit) query.append("limit", params.limit.toString());
    if (params?.offset) query.append("offset", params.offset.toString());
    const qs = query.toString() ? `?${query.toString()}` : "";
    return typedFetch<TicketListResponse>(`/api/v1/organizations/${orgId}/tickets${qs}`);
  },

  /**
   * Create a support ticket
   */
  async createTicket(orgId: string, payload: TicketCreatePayload): Promise<Ticket> {
    return typedFetch<Ticket>(`/api/v1/organizations/${orgId}/tickets`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Retrieve ticket by ID
   */
  async getTicket(orgId: string, ticketId: string): Promise<Ticket> {
    return typedFetch<Ticket>(`/api/v1/organizations/${orgId}/tickets/${ticketId}`);
  },

  /**
   * Update mutable ticket fields
   */
  async updateTicket(orgId: string, ticketId: string, payload: TicketUpdatePayload): Promise<Ticket> {
    return typedFetch<Ticket>(`/api/v1/organizations/${orgId}/tickets/${ticketId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  /**
   * List conversations for a ticket
   */
  async listTicketConversations(orgId: string, ticketId: string): Promise<ConversationListResponse> {
    return typedFetch<ConversationListResponse>(`/api/v1/organizations/${orgId}/tickets/${ticketId}/conversations`);
  },

  /**
   * List messages in a conversation
   */
  async listMessages(orgId: string, convId: string): Promise<MessageListResponse> {
    return typedFetch<MessageListResponse>(`/api/v1/organizations/${orgId}/conversations/${convId}/messages`);
  },

  /**
   * Append a message to a conversation
   */
  async createMessage(orgId: string, convId: string, payload: MessageCreatePayload): Promise<Message> {
    return typedFetch<Message>(`/api/v1/organizations/${orgId}/conversations/${convId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * List active knowledge bases for an organization
   */
  async listKnowledgeBases(orgId: string): Promise<KnowledgeBaseListResponse> {
    return typedFetch<KnowledgeBaseListResponse>(`/api/v1/organizations/${orgId}/knowledge-bases`);
  },

  /**
   * Search knowledge base collections with ranked evidence
   */
  async searchKnowledge(
    orgId: string,
    kbId: string | null,
    query: string,
    topK: number = 5,
    minScore?: number
  ): Promise<KnowledgeSearchResponse> {
    const endpoint = kbId
      ? `/api/v1/organizations/${orgId}/knowledge-bases/${kbId}/search`
      : `/api/v1/organizations/${orgId}/knowledge/search`;
    return typedFetch<KnowledgeSearchResponse>(endpoint, {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK, min_score: minScore }),
    });
  },

  /**
   * Ask an evidence-grounded question with verified citations and abstention
   */
  async askKnowledge(
    orgId: string,
    kbId: string | null,
    question: string,
    topK: number = 5,
    minScore?: number
  ): Promise<KnowledgeAnswerResponse> {
    const endpoint = kbId
      ? `/api/v1/organizations/${orgId}/knowledge-bases/${kbId}/answer`
      : `/api/v1/organizations/${orgId}/knowledge/answer`;
    return typedFetch<KnowledgeAnswerResponse>(endpoint, {
      method: "POST",
      body: JSON.stringify({ question, top_k: topK, min_score: minScore }),
    });
  },

  /**
   * List response drafts for an organization
   */
  async listDrafts(orgId: string, ticketId?: string): Promise<{ items: ResponseDraft[]; total: number }> {
    const qs = ticketId ? `?ticket_id=${ticketId}` : "";
    return typedFetch<{ items: ResponseDraft[]; total: number }>(`/api/v1/organizations/${orgId}/drafts${qs}`);
  },

  /**
   * Create a response draft
   */
  async createDraft(
    orgId: string,
    payload: {
      original_query: string;
      draft_text: string;
      ticket_id?: string | null;
      conversation_id?: string | null;
      evidence_references?: Array<Record<string, unknown>>;
    }
  ): Promise<ResponseDraft> {
    return typedFetch<ResponseDraft>(`/api/v1/organizations/${orgId}/drafts`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Revise an existing response draft (increments version and invalidates approvals)
   */
  async reviseDraft(
    orgId: string,
    draftId: string,
    payload: {
      draft_text: string;
      evidence_references?: Array<Record<string, unknown>>;
    }
  ): Promise<ResponseDraft> {
    return typedFetch<ResponseDraft>(`/api/v1/organizations/${orgId}/drafts/${draftId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Run verification pipeline against a draft
   */
  async verifyDraft(orgId: string, draftId: string): Promise<VerificationRun> {
    return typedFetch<VerificationRun>(`/api/v1/organizations/${orgId}/drafts/${draftId}/verify`, {
      method: "POST",
    });
  },

  /**
   * Retrieve a specific verification run
   */
  async getVerificationRun(orgId: string, runId: string): Promise<VerificationRun> {
    return typedFetch<VerificationRun>(`/api/v1/organizations/${orgId}/verification-runs/${runId}`);
  },

  /**
   * List organizational policy rules
   */
  async listPolicies(orgId: string): Promise<{ items: PolicyRule[]; total: number }> {
    return typedFetch<{ items: PolicyRule[]; total: number }>(`/api/v1/organizations/${orgId}/policies`);
  },

  /**
   * Create a new policy rule
   */
  async createPolicy(
    orgId: string,
    payload: {
      name: string;
      description?: string;
      policy_category: string;
      severity: string;
      rule_type: string;
      rule_config: Record<string, unknown>;
      is_enabled?: boolean;
    }
  ): Promise<PolicyRule> {
    return typedFetch<PolicyRule>(`/api/v1/organizations/${orgId}/policies`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Toggle a policy rule enabled/disabled
   */
  async togglePolicy(orgId: string, policyId: string): Promise<PolicyRule> {
    return typedFetch<PolicyRule>(`/api/v1/organizations/${orgId}/policies/${policyId}/toggle`, {
      method: "PATCH",
    });
  },

  /**
   * List human approval requests
   */
  async listApprovals(orgId: string, status?: string): Promise<{ items: ApprovalRequest[]; total: number }> {
    const qs = status ? `?status=${status}` : "";
    return typedFetch<{ items: ApprovalRequest[]; total: number }>(`/api/v1/organizations/${orgId}/approvals${qs}`);
  },

  /**
   * Submit draft for human approval
   */
  async createApprovalRequest(
    orgId: string,
    draftId: string,
    payload: {
      draft_version: number;
      verification_run_id: string;
      required_role?: string;
      separation_of_duties?: boolean;
    }
  ): Promise<ApprovalRequest> {
    return typedFetch<ApprovalRequest>(`/api/v1/organizations/${orgId}/drafts/${draftId}/approvals`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Submit human approval decision
   */
  async decideApproval(
    orgId: string,
    approvalId: string,
    payload: {
      decision: "approve" | "reject" | "request_revision";
      reason?: string;
    }
  ): Promise<ApprovalRequest> {
    return typedFetch<ApprovalRequest>(`/api/v1/organizations/${orgId}/approvals/${approvalId}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Query append-only audit trail
   */
  async listAuditTrail(orgId: string, entityType?: string): Promise<{ items: VerificationAuditEvent[]; total: number }> {
    const qs = entityType ? `?entity_type=${entityType}` : "";
    return typedFetch<{ items: VerificationAuditEvent[]; total: number }>(`/api/v1/organizations/${orgId}/verification-audit${qs}`);
  },

  // ==========================================
  // Phase 08: Observability, Diagnostics & Evaluations
  // ==========================================

  /**
   * Deep system and dependency diagnostics (non-blocking, zero paid LLM calls)
   */
  async getDiagnostics(orgId: string): Promise<SystemDiagnostics> {
    return typedFetch<SystemDiagnostics>(`/api/v1/organizations/${orgId}/observability/diagnostics`);
  },

  /**
   * Query execution traces
   */
  async listTraces(
    orgId: string,
    params?: { operation_type?: string; outcome?: string; limit?: number; offset?: number }
  ): Promise<{ items: TraceSummary[]; total: number }> {
    const query = new URLSearchParams();
    if (params?.operation_type) query.set("operation_type", params.operation_type);
    if (params?.outcome) query.set("outcome", params.outcome);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString() ? `?${query.toString()}` : "";
    return typedFetch<{ items: TraceSummary[]; total: number }>(`/api/v1/organizations/${orgId}/observability/traces${qs}`);
  },

  /**
   * Fetch single execution trace with spans and correlation metadata
   */
  async getTrace(orgId: string, traceId: string): Promise<TraceDetail> {
    return typedFetch<TraceDetail>(`/api/v1/organizations/${orgId}/observability/traces/${traceId}`);
  },

  /**
   * List deduplicated failure investigations
   */
  async listInvestigations(
    orgId: string,
    params?: { status?: string; category?: string; limit?: number; offset?: number }
  ): Promise<{ items: FailureInvestigation[]; total: number }> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.category) query.set("category", params.category);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.offset) query.set("offset", String(params.offset));
    const qs = query.toString() ? `?${query.toString()}` : "";
    return typedFetch<{ items: FailureInvestigation[]; total: number }>(`/api/v1/organizations/${orgId}/observability/investigations${qs}`);
  },

  /**
   * Fetch a single failure investigation record
   */
  async getInvestigation(orgId: string, investigationId: string): Promise<FailureInvestigation> {
    return typedFetch<FailureInvestigation>(`/api/v1/organizations/${orgId}/observability/investigations/${investigationId}`);
  },

  /**
   * Update failure investigation status and resolution notes
   */
  async updateInvestigation(
    orgId: string,
    investigationId: string,
    payload: { status?: string; resolution_notes?: string }
  ): Promise<FailureInvestigation> {
    return typedFetch<FailureInvestigation>(`/api/v1/organizations/${orgId}/observability/investigations/${investigationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  /**
   * List reproducible benchmark evaluation runs
   */
  async listEvaluations(
    orgId: string,
    datasetId?: string
  ): Promise<{ items: EvaluationRunRecord[]; total: number }> {
    const qs = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : "";
    return typedFetch<{ items: EvaluationRunRecord[]; total: number }>(`/api/v1/organizations/${orgId}/observability/evaluations${qs}`);
  },

  /**
   * Trigger a new benchmark evaluation run
   */
  async createEvaluationRun(
    orgId: string,
    payload: {
      dataset_id: string;
      dataset_version: string;
      embedding_model?: string;
      generation_model?: string;
      regression_threshold_pct?: number;
    }
  ): Promise<EvaluationRunRecord> {
    return typedFetch<EvaluationRunRecord>(`/api/v1/organizations/${orgId}/observability/evaluations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Compare two evaluation runs to assess regressions
   */
  async compareEvaluations(
    orgId: string,
    currentRunId: string,
    baselineRunId: string,
    thresholdPct: number = 5.0
  ): Promise<EvaluationComparison> {
    return typedFetch<EvaluationComparison>(`/api/v1/organizations/${orgId}/observability/evaluations/compare`, {
      method: "POST",
      body: JSON.stringify({
        current_run_id: currentRunId,
        baseline_run_id: baselineRunId,
        regression_threshold_pct: thresholdPct,
      }),
    });
  },

  /**
   * Get tenant usage summary with token consumption and cost breakdown
   */
  async getUsageSummary(orgId: string): Promise<UsageSummary> {
    return typedFetch<UsageSummary>(`/api/v1/organizations/${orgId}/observability/usage`);
  },
};

