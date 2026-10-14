"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { Badge } from "../ui/Badge";

export interface NavigationItemProps {
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: {
    text: string;
    variant: "success" | "warning" | "danger" | "info" | "neutral" | "brand";
  };
}

export function NavigationItem({
  label,
  href,
  icon,
  badge,
}: NavigationItemProps) {
  const pathname = usePathname();
  const isActive = pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      className={clsx(
        "flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-all group",
        isActive
          ? "bg-indigo-600/15 text-indigo-400 border border-indigo-500/30"
          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
      )}
    >
      <div className="flex items-center gap-3">
        <span
          className={clsx(
            "transition-colors",
            isActive
              ? "text-indigo-400"
              : "text-slate-500 group-hover:text-slate-300"
          )}
        >
          {icon}
        </span>
        <span>{label}</span>
      </div>
      {badge && (
        <Badge variant={badge.variant} size="sm">
          {badge.text}
        </Badge>
      )}
    </Link>
  );
}
