import React from "react";
import { Card, CardHeader, CardContent } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { CheckCircle2, AlertTriangle, XCircle, Clock } from "lucide-react";

export interface HealthStatusCardProps {
  title: string;
  status: "up" | "down" | "degraded" | "checking" | "ready";
  latencyMs?: number | null;
  description: string;
  errorMessage?: string | null;
}

export function HealthStatusCard({
  title,
  status,
  latencyMs,
  description,
  errorMessage,
}: HealthStatusCardProps) {
  const getBadge = () => {
    switch (status) {
      case "up":
      case "ready":
        return (
          <Badge variant="success" size="sm">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Operational
          </Badge>
        );
      case "degraded":
        return (
          <Badge variant="warning" size="sm">
            <AlertTriangle className="w-3 h-3 mr-1" />
            Degraded
          </Badge>
        );
      case "down":
        return (
          <Badge variant="danger" size="sm">
            <XCircle className="w-3 h-3 mr-1" />
            Unreachable
          </Badge>
        );
      default:
        return (
          <Badge variant="neutral" size="sm">
            Checking...
          </Badge>
        );
    }
  };

  return (
    <Card className="flex flex-col justify-between">
      <div>
        <CardHeader title={title} action={getBadge()} />
        <CardContent>
          <p className="text-xs text-slate-400 mb-4">{description}</p>
          {errorMessage && (
            <div className="p-2.5 rounded bg-rose-950/30 border border-rose-900/50 text-[11px] text-rose-300 font-mono break-all mb-3">
              {errorMessage}
            </div>
          )}
        </CardContent>
      </div>

      <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          Latency
        </span>
        <span className="font-mono text-slate-200">
          {latencyMs !== undefined && latencyMs !== null
            ? `${latencyMs.toFixed(1)} ms`
            : "—"}
        </span>
      </div>
    </Card>
  );
}
