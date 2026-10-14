/**
 * TypeScript API contracts matching backend Pydantic schemas.
 */

export interface HealthStatusResponse {
  status: "ok";
  app: string;
  environment: string;
  version: string;
  timestamp: string;
}

export type DependencyStatus = "up" | "down" | "skipped" | "degraded";

export interface DependencyHealth {
  status: DependencyStatus;
  latency_ms: number | null;
  error: string | null;
}

export interface ReadinessResponse {
  status: "ready" | "degraded";
  environment: string;
  dependencies: Record<string, DependencyHealth>;
  timestamp: string;
}

export interface SystemInfoResponse {
  app_name: string;
  version: string;
  environment: string;
  phase: string;
  architecture: string;
  docs_url: string;
}

export interface ErrorDetail {
  field: string | null;
  message: string;
  code: string | null;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: ErrorDetail[];
  request_id: string | null;
  timestamp: string;
}

export interface ErrorResponse {
  error: ErrorBody;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
  last_login_at?: string | null;
}

export interface UserOrganizationSummary {
  organization_id: string;
  name: string;
  slug: string;
  role: string;
  status: string;
}

export interface LoginResponse {
  user: UserProfile;
  expires_at: string;
  token?: string | null;
  organizations: UserOrganizationSummary[];
}

export interface CurrentUserResponse {
  user: UserProfile;
  organizations: UserOrganizationSummary[];
}

export interface LogoutResponse {
  message: string;
}

export type TicketStatus = "open" | "pending" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "urgent" | "high" | "medium" | "low";
export type TicketChannel = "email" | "chat" | "api" | "web" | "internal";

export interface Ticket {
  id: string;
  organization_id: string;
  customer_id: string | null;
  ticket_number: number;
  ticket_reference: string;
  subject: string;
  status: TicketStatus;
  priority: TicketPriority;
  channel: TicketChannel;
  assigned_actor_id: string | null;
  first_response_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  external_reference: string | null;
  lock_version: number;
  created_at: string;
  updated_at: string;
}

export interface TicketListResponse {
  items: Ticket[];
  total: number;
  limit: number;
  offset: number;
}

export interface TicketCreatePayload {
  subject: string;
  description?: string;
  priority?: TicketPriority;
  channel?: TicketChannel;
  customer_id?: string;
  assigned_actor_id?: string;
}

export interface TicketUpdatePayload {
  subject?: string;
  status?: TicketStatus;
  priority?: TicketPriority;
  assigned_actor_id?: string | null;
  customer_id?: string | null;
  lock_version?: number;
}

export interface Conversation {
  id: string;
  organization_id: string;
  ticket_id: string;
  channel_type: TicketChannel;
  external_thread_id: string | null;
  status: string;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
}

export interface Message {
  id: string;
  organization_id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  author_type: "customer" | "agent" | "system" | "ai";
  author_id: string | null;
  sender_display_name: string | null;
  body_text: string;
  sequence_number: number;
  delivery_status: string;
  created_at: string;
  provider_sent_at?: string | null;
}

export interface MessageListResponse {
  items: Message[];
  total: number;
  limit: number;
  offset: number;
}

export interface MessageCreatePayload {
  body_text: string;
  direction?: "inbound" | "outbound";
  author_type?: "customer" | "agent" | "system" | "ai";
  content_type?: string;
}

export interface Customer {
  id: string;
  organization_id: string;
  display_name: string;
  company_name: string | null;
  external_customer_id: string | null;
  status: string;
  created_at: string;
}

export interface CustomerListResponse {
  items: Customer[];
  total: number;
  limit: number;
  offset: number;
}

