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

