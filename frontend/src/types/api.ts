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

export interface KnowledgeBase {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseListResponse {
  items: KnowledgeBase[];
  total: number;
}

export interface EvidenceItem {
  evidence_id: string;
  chunk_id: string;
  document_id: string;
  document_version_id: string;
  knowledge_base_id: string;
  source_title: string;
  section_title: string | null;
  heading_hierarchy: string[];
  relevant_excerpt: string;
  retrieval_rank: number;
  retrieval_score: number;
  scoring_method: string;
  citation_reference: string;
}

export interface KnowledgeSearchResponse {
  query: string;
  evidence: EvidenceItem[];
  total_results: number;
  retrieval_latency_ms: number;
}

export interface CitationItem {
  citation_number: number;
  citation_marker: string;
  evidence_id: string;
  chunk_id: string;
  document_id: string;
  source_title: string;
  section_title: string | null;
  excerpt: string;
  retrieval_score: number;
}

export interface KnowledgeAnswerResponse {
  question: string;
  answer: string;
  citations: CitationItem[];
  evidence: EvidenceItem[];
  abstention_status: boolean;
  abstention_reason: string | null;
  model_name: string | null;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  total_latency_ms: number;
}

// ============================================================================
// Phase 07: Response Verification, Policy Enforcement & Human Approval
// ============================================================================

export type DraftLifecycleStatus =
  | 'draft'
  | 'verification_pending'
  | 'verified'
  | 'verification_failed'
  | 'approval_pending'
  | 'approved'
  | 'revision_required'
  | 'rejected'
  | 'superseded';

export type VerificationStatus =
  | 'passed'
  | 'passed_with_warnings'
  | 'needs_revision'
  | 'blocked'
  | 'failed';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type ClaimCategory =
  | 'policy'
  | 'pricing_refund'
  | 'sla_commitment'
  | 'product_fact'
  | 'general';

export type ClaimSupportStatus =
  | 'supported'
  | 'partially_supported'
  | 'unsupported'
  | 'contradicted'
  | 'not_verifiable';

export type ClaimVerificationMethod =
  | 'evidence_grounding'
  | 'deterministic_rule'
  | 'model_assisted';

export type PolicyCategory =
  | 'factual_accuracy'
  | 'evidence_citations'
  | 'sensitive_data'
  | 'restricted_commitments'
  | 'refund_compensation'
  | 'escalation_required'
  | 'required_disclaimers'
  | 'prohibited_terms'
  | 'approval_thresholds';

export type PolicyRuleType =
  | 'unsupported_claim_block'
  | 'keyword_prohibition'
  | 'required_phrase'
  | 'max_length'
  | 'refund_limit'
  | 'mandatory_approval_on_risk';

export type PolicySeverity = 'low' | 'medium' | 'high' | 'critical';

export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'revision_requested'
  | 'invalidated'
  | 'cancelled';

export interface ResponseDraft {
  id: string;
  organization_id: string;
  ticket_id?: string | null;
  conversation_id?: string | null;
  original_query: string;
  draft_text: string;
  version_number: number;
  lifecycle_status: DraftLifecycleStatus;
  evidence_references: Array<{
    chunk_id?: string;
    excerpt?: string;
    source_title?: string;
    [key: string]: unknown;
  }>;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClaimFinding {
  id: string;
  claim_text: string;
  claim_category: ClaimCategory;
  support_status: ClaimSupportStatus;
  evidence_chunk_ids: string[];
  confidence_score?: number | null;
  reason: string;
  verification_method: ClaimVerificationMethod;
}

export interface VerificationRun {
  id: string;
  draft_id: string;
  draft_version: number;
  verification_pipeline_version: string;
  policy_set_version: number;
  status: VerificationStatus;
  risk_level: RiskLevel;
  requires_human_approval: boolean;
  machine_readable_findings: Record<string, unknown>;
  claim_findings: ClaimFinding[];
  evidence_references: unknown[];
  started_at: string;
  completed_at?: string | null;
  execution_time_ms: number;
  error_message?: string | null;
}

export interface PolicyRule {
  id: string;
  name: string;
  description?: string | null;
  policy_category: PolicyCategory;
  severity: PolicySeverity;
  rule_type: PolicyRuleType;
  rule_config: Record<string, unknown>;
  is_enabled: boolean;
  version_number: number;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRequest {
  id: string;
  draft_id: string;
  draft_version: number;
  verification_run_id: string;
  status: ApprovalStatus;
  required_role: string;
  separation_of_duties: boolean;
  assigned_to_user_id?: string | null;
  requested_by_user_id?: string | null;
  decision_by_user_id?: string | null;
  decision_reason?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface VerificationAuditEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor_id?: string | null;
  request_id?: string | null;
  event_summary: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
}


