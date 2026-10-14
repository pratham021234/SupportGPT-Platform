"use client";

import React, { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { Badge } from "../ui/Badge";
import { Server, ExternalLink, RefreshCw } from "lucide-react";

export function AppHeader() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");
  const [appEnv, setAppEnv] = useState<string>("development");

  const checkLiveness = async () => {
    try {
      const data = await apiClient.getLiveness();
      if (data.status === "ok") {
        setBackendStatus("online");
        setAppEnv(data.environment);
      } else {
        setBackendStatus("offline");
      }
    } catch {
      setBackendStatus("offline");
    }
  };

  useEffect(() => {
    checkLiveness();
    const interval = setInterval(checkLiveness, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-20">
      {/* Left: Active Workspace Indicator */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <span className="font-semibold text-slate-100">Default Workspace</span>
          <span className="text-slate-600">/</span>
          <span className="text-xs text-slate-400">Foundation Mode</span>
        </div>
        <Badge variant="brand" size="sm">
          Phase 00
        </Badge>
      </div>

      {/* Right: Backend Connection Status, Environment & Documentation Link */}
      <div className="flex items-center gap-4 text-xs">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
          <Server className="w-3.5 h-3.5 text-slate-400" />
          <span>Backend:</span>
          {backendStatus === "checking" && (
            <Badge variant="warning" size="sm">
              <RefreshCw className="w-2.5 h-2.5 animate-spin" />
              Checking
            </Badge>
          )}
          {backendStatus === "online" && (
            <Badge variant="success" size="sm">
              Online
            </Badge>
          )}
          {backendStatus === "offline" && (
            <Badge variant="danger" size="sm">
              Disconnected
            </Badge>
          )}
        </div>

        <div className="px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-slate-400 font-mono uppercase text-[11px]">
          {appEnv}
        </div>

        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <span>OpenAPI Docs</span>
          <ExternalLink className="w-3 h-3 text-slate-400" />
        </a>
      </div>
    </header>
  );
}
