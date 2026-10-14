"use client";

import React from "react";
import {
  Activity,
  ShieldCheck,
  Inbox,
  BookOpen,
  CheckCircle,
  AlertOctagon,
  BarChart3,
  Settings,
  Layers,
} from "lucide-react";
import { NavigationItem } from "./NavigationItem";

export function AppSidebar() {
  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-950/95 flex flex-col h-screen fixed left-0 top-0 z-30 select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-5 border-b border-slate-800 gap-3">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black text-white text-base shadow-sm shadow-indigo-500/30">
          S
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-slate-100 text-sm tracking-tight">
            SupportGPT AI
          </span>
          <span className="text-[11px] text-indigo-400 font-medium">
            Enterprise Reliability
          </span>
        </div>
      </div>

      {/* Navigation Scroll Area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Foundation & System Group */}
        <div>
          <div className="px-3 mb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
            Platform Foundation
          </div>
          <div className="space-y-1">
            <NavigationItem
              label="Platform Overview"
              href="/"
              icon={<Layers className="w-4 h-4" />}
            />
            <NavigationItem
              label="System Diagnostics"
              href="/system"
              icon={<Activity className="w-4 h-4" />}
              badge={{ text: "Active", variant: "success" }}
            />
          </div>
        </div>

        {/* Core Product Roadmap Modules */}
        <div>
          <div className="px-3 mb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
            Planned Modules
          </div>
          <div className="space-y-1">
            <NavigationItem
              label="Support Inbox"
              href="/modules/inbox"
              icon={<Inbox className="w-4 h-4" />}
              badge={{ text: "Phase 03", variant: "neutral" }}
            />
            <NavigationItem
              label="Knowledge Engine"
              href="/modules/knowledge"
              icon={<BookOpen className="w-4 h-4" />}
              badge={{ text: "Phase 04", variant: "neutral" }}
            />
            <NavigationItem
              label="Response Verification"
              href="/modules/verification"
              icon={<ShieldCheck className="w-4 h-4" />}
              badge={{ text: "Phase 05", variant: "neutral" }}
            />
            <NavigationItem
              label="Human Approvals"
              href="/modules/approvals"
              icon={<CheckCircle className="w-4 h-4" />}
              badge={{ text: "Phase 06", variant: "neutral" }}
            />
            <NavigationItem
              label="Failure Investigation"
              href="/modules/investigation"
              icon={<AlertOctagon className="w-4 h-4" />}
              badge={{ text: "Phase 07", variant: "neutral" }}
            />
            <NavigationItem
              label="AI Evaluation"
              href="/modules/analytics"
              icon={<BarChart3 className="w-4 h-4" />}
              badge={{ text: "Phase 08", variant: "neutral" }}
            />
          </div>
        </div>

        {/* Administration */}
        <div>
          <div className="px-3 mb-2 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
            Administration
          </div>
          <div className="space-y-1">
            <NavigationItem
              label="Tenancy & RLS"
              href="/modules/tenancy"
              icon={<Settings className="w-4 h-4" />}
              badge={{ text: "Phase 02", variant: "neutral" }}
            />
          </div>
        </div>
      </div>

      {/* Footer / Engineering Release Badge */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-900/40">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Phase 00 Foundation</span>
          <span className="font-mono text-[11px] text-slate-500">v0.1.0</span>
        </div>
        <div className="mt-1 text-[11px] text-slate-500">
          Strict Engineering Baseline
        </div>
      </div>
    </aside>
  );
}
