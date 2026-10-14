import React from "react";
import type { DependencyHealth } from "@/types/api";
import { Badge } from "../ui/Badge";
import { Database, Zap, Cpu } from "lucide-react";

export interface ServiceCheckTableProps {
  dependencies: Record<string, DependencyHealth>;
}

export function ServiceCheckTable({ dependencies }: ServiceCheckTableProps) {
  const getIcon = (name: string) => {
    switch (name.toLowerCase()) {
      case "database":
        return <Database className="w-4 h-4 text-indigo-400" />;
      case "redis":
        return <Zap className="w-4 h-4 text-amber-400" />;
      case "qdrant":
        return <Cpu className="w-4 h-4 text-sky-400" />;
      default:
        return <Database className="w-4 h-4 text-slate-400" />;
    }
  };

  const entries = Object.entries(dependencies);

  if (entries.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-slate-500 bg-slate-900/40 rounded-xl border border-slate-800">
        No external dependencies probed.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
      <table className="w-full text-left text-sm text-slate-300">
        <thead className="bg-slate-950/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
          <tr>
            <th className="px-5 py-3.5 font-semibold">Service Name</th>
            <th className="px-5 py-3.5 font-semibold">Probed Status</th>
            <th className="px-5 py-3.5 font-semibold">Latency</th>
            <th className="px-5 py-3.5 font-semibold">Operational Diagnostics</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/80">
          {entries.map(([name, check]) => {
            const isUp = check.status === "up";
            const isDegraded = check.status === "degraded";

            return (
              <tr key={name} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-5 py-4 font-medium text-slate-100 flex items-center gap-2.5">
                  {getIcon(name)}
                  <span className="capitalize">{name}</span>
                </td>
                <td className="px-5 py-4">
                  {isUp && <Badge variant="success">Operational</Badge>}
                  {isDegraded && <Badge variant="warning">Degraded</Badge>}
                  {!isUp && !isDegraded && <Badge variant="danger">Unreachable</Badge>}
                </td>
                <td className="px-5 py-4 font-mono text-xs">
                  {check.latency_ms !== null ? `${check.latency_ms.toFixed(1)} ms` : "—"}
                </td>
                <td className="px-5 py-4 text-xs font-mono text-slate-400">
                  {check.error ? (
                    <span className="text-rose-400 truncate max-w-xs block">
                      {check.error}
                    </span>
                  ) : (
                    <span className="text-emerald-400">Health probe passed</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
