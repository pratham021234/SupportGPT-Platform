import React from "react";
import { clsx } from "clsx";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: "success" | "warning" | "danger" | "info" | "neutral" | "brand";
  size?: "sm" | "md";
  className?: string;
}

export function Badge({
  children,
  variant = "neutral",
  size = "sm",
  className,
}: BadgeProps) {
  const variantStyles = {
    success: "bg-emerald-950/70 text-emerald-400 border-emerald-800/60",
    warning: "bg-amber-950/70 text-amber-400 border-amber-800/60",
    danger: "bg-rose-950/70 text-rose-400 border-rose-800/60",
    info: "bg-sky-950/70 text-sky-400 border-sky-800/60",
    neutral: "bg-slate-800/70 text-slate-300 border-slate-700/60",
    brand: "bg-indigo-950/70 text-indigo-300 border-indigo-800/60",
  };

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs font-medium",
    md: "px-2.5 py-1 text-sm font-medium",
  };

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border transition-colors",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
    >
      {children}
    </span>
  );
}
