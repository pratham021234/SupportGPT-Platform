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
