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
};

