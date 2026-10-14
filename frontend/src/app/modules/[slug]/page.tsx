import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import {
  ArrowLeft,
  Calendar,
  Lock,
} from "lucide-react";

interface ModuleConfig {
  name: string;
  phase: string;
  description: string;
  prerequisites: string[];
  securityRequirements: string[];
  iconName: string;
}

const MODULE_REGISTRY: Record<string, ModuleConfig> = {
  inbox: {
    name: "Support Inbox & Conversations",
    phase: "Phase 03",
    description:
      "Persistent omnichannel support inbox managing customer threads, message lifecycle, status transitions, and agent assignment.",
    prerequisites: [
      "Phase 00 Foundation & DB conventions (Completed)",
      "Phase 01 Multi-channel data ingestion model",
      "Phase 02 Multi-tenant organizations and membership auth",
    ],
    securityRequirements: [
      "Strict Row-Level Security isolating customer conversation threads per tenant",
      "Sanitization of incoming customer message payloads",
    ],
    iconName: "Inbox",
  },
  knowledge: {
    name: "Company Knowledge Engine",
    phase: "Phase 04",
    description:
      "Document ingestion, chunking, embedding generation, Qdrant vector retrieval, and versioned truth indexing.",
    prerequisites: [
      "Phase 00 Qdrant container and BaseEmbeddingProvider interface (Completed)",
      "Phase 02 Organization-isolated document partitions",
    ],
    securityRequirements: [
      "Tenant-isolated vector collections in Qdrant",
      "Document access controls ensuring non-public documents are excluded from retrieval context",
    ],
    iconName: "BookOpen",
  },
  verification: {
    name: "Claim-Level Response Verification",
    phase: "Phase 05",
    description:
      "Decomposes candidate AI responses into atomic claims, retrieves source grounding evidence, and detects factual contradictions before output.",
    prerequisites: [
      "Phase 00 AI Action Proposal interface (Completed)",
      "Phase 04 Knowledge engine vector retrieval",
    ],
    securityRequirements: [
      "Zero ungrounded hallucinations permitted to bypass verification threshold",
      "Contradiction detection against canonical enterprise policies",
    ],
    iconName: "ShieldCheck",
  },
  approvals: {
    name: "Policy-Enforced Human Approvals",
    phase: "Phase 06",
    description:
      "Interception gateway requiring human agent approval for high-risk actions, refunds, policy exceptions, or low-confidence responses.",
    prerequisites: [
      "Phase 00 AIActionProposal invariant (Completed)",
      "Phase 02 Role-based access control (RBAC)",
      "Phase 03 Support inbox action stream",
    ],
    securityRequirements: [
      "AI-generated actions are proposals only; authorization authority resides solely in authenticated human agents",
      "Audit trail logging of all approvals and rejections",
    ],
    iconName: "CheckCircle",
  },
  investigation: {
    name: "Root-Cause Failure Investigation",
    phase: "Phase 07",
    description:
      "Forensic diagnostics for AI failures: tracing retrieval gaps, prompt drift, claim contradictions, and workflow errors.",
    prerequisites: [
      "Phase 00 Structured error envelope and request correlation IDs (Completed)",
      "Phase 05 Verification failure telemetry",
    ],
    securityRequirements: [
      "Redaction of customer PII in failure trace logs",
      "Immutable audit records for compliance investigations",
    ],
    iconName: "AlertOctagon",
  },
  analytics: {
    name: "Operational Analytics & AI Evaluation",
    phase: "Phase 08",
    description:
      "Repeatable evaluation datasets, accuracy benchmarks, latency distribution, and operational metrics.",
    prerequisites: [
      "Phase 00 System metrics baseline (Completed)",
      "Phase 03-07 Telemetry events",
    ],
    securityRequirements: [
      "Aggregated reporting without cross-tenant data leakage",
      "Statistical metrics grounded only in real recorded events",
    ],
    iconName: "BarChart3",
  },
  tenancy: {
    name: "Multi-Tenancy & Row-Level Security",
    phase: "Phase 02",
    description:
      "PostgreSQL Row-Level Security policies, organization workspaces, user memberships, and transaction-local tenant context.",
    prerequisites: [
      "Phase 00 SQLAlchemy 2.x session lifecycle and naming conventions (Completed)",
    ],
    securityRequirements: [
      "Transaction-local SET LOCAL app.current_tenant_id enforced on every query",
      "Adversarial tenant-isolation test suite before declaring tenancy complete",
    ],
    iconName: "Settings",
  },
};

export default async function ModuleRoadmapPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const config = MODULE_REGISTRY[slug];

  if (!config) {
    notFound();
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back button */}
      <div>
        <Link
          href="/"
          className="inline-flex items-center text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1" />
          Back to Platform Overview
        </Link>
      </div>

      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="neutral" size="md">
            <Calendar className="w-3 h-3 mr-1" />
            {config.phase} Milestone
          </Badge>
          <Badge variant="warning" size="md">
            Implementation Pending
          </Badge>
        </div>
        <h1 className="text-2xl font-bold text-white">{config.name}</h1>
        <p className="text-sm text-slate-400 leading-relaxed">
          {config.description}
        </p>
      </div>

      {/* Honest Availability Notice */}
      <Alert
        variant="info"
        title="Engineering Milestone: Feature Scheduled for Future Phase"
      >
        This module is currently in the architectural planning phase. In accordance
        with our product standards, nonfunctional controls are not simulated with fake
        data. The underlying technical contracts and foundations for this domain were
        established in Phase 00.
      </Alert>

      {/* Architectural Prerequisites & Security */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Card>
          <CardHeader
            title="Architectural Prerequisites"
            subtitle="Foundation requirements before implementation"
          />
          <CardContent className="space-y-2">
            <ul className="space-y-2 text-xs text-slate-300">
              {config.prerequisites.map((req, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 flex-shrink-0" />
                  <span>{req}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Security Requirements"
            subtitle="Mandatory security controls for this module"
          />
          <CardContent className="space-y-2">
            <ul className="space-y-2 text-xs text-slate-300">
              {config.securityRequirements.map((sec, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <Lock className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                  <span>{sec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
