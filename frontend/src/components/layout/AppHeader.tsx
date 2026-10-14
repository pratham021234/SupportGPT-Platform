"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api";
import { Badge } from "../ui/Badge";
import { Server, ExternalLink, RefreshCw, UserCheck, LogOut, LogIn } from "lucide-react";
import type { CurrentUserResponse } from "@/types/api";

export function AppHeader() {
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");
  const [appEnv, setAppEnv] = useState<string>("development");
  const [currentUser, setCurrentUser] = useState<CurrentUserResponse | null>(null);
  const [authChecking, setAuthChecking] = useState<boolean>(true);

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

  const loadUser = async () => {
    setAuthChecking(true);
    try {
      const userRes = await apiClient.getCurrentUser();
      setCurrentUser(userRes);
    } catch {
      setCurrentUser(null);
    } finally {
      setAuthChecking(false);
    }
  };

  const handleLogout = async () => {
    try {
      await apiClient.logout();
    } catch {
      // Ignored
    } finally {
      setCurrentUser(null);
      window.location.reload();
    }
  };

  useEffect(() => {
    checkLiveness();
    loadUser();
    const interval = setInterval(checkLiveness, 15000);
    return () => clearInterval(interval);
  }, []);

  const activeOrg = currentUser?.organizations?.[0];

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-950/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-20">
      {/* Left: Active Workspace & Tenant Indicator */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2 text-sm text-slate-300 hover:text-white transition-colors">
          <span className="font-semibold text-slate-100 font-mono">SupportGPT</span>
          <span className="text-slate-600">/</span>
          {activeOrg ? (
            <span className="text-xs font-medium text-cyan-400">{activeOrg.name}</span>
          ) : (
            <span className="text-xs text-slate-400">Default Workspace</span>
          )}
        </Link>
        <Link
          href="/tickets"
          className="text-xs px-2.5 py-1 rounded-md bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 hover:bg-indigo-500/20 transition-colors font-medium"
        >
          Tickets Console
        </Link>
        <Badge variant="brand" size="sm">
          Phase 03 &bull; Ticket Operations
        </Badge>
      </div>

      {/* Right: Auth Profile, Backend Status, Docs Link */}
      <div className="flex items-center gap-3 text-xs">
        {/* User Identity / Auth State */}
        {!authChecking && (
          <div>
            {currentUser ? (
              <div className="flex items-center gap-2 pl-3 pr-2 py-1 bg-slate-900 border border-slate-800 rounded-lg">
                <div className="flex items-center gap-1.5 text-slate-300">
                  <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="font-medium text-slate-200">{currentUser.user.display_name}</span>
                </div>
                {activeOrg && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-cyan-950 border border-cyan-800 text-cyan-300">
                    {activeOrg.role}
                  </span>
                )}
                <button
                  onClick={handleLogout}
                  title="Sign out of current session"
                  className="p-1 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded transition-colors"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/20 hover:text-cyan-200 transition-colors font-medium"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Operator Sign In</span>
              </Link>
            )}
          </div>
        )}

        {/* Backend Connectivity Status */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
          <Server className="w-3.5 h-3.5 text-slate-400" />
          <span className="hidden sm:inline">Backend:</span>
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
              Offline
            </Badge>
          )}
        </div>

        <div className="hidden sm:block px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-slate-400 font-mono uppercase text-[11px]">
          {appEnv}
        </div>

        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <span className="hidden sm:inline">API</span> Docs
          <ExternalLink className="w-3 h-3 text-slate-400" />
        </a>
      </div>
    </header>
  );
}
