import React from "react";
import { clsx } from "clsx";

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        "bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-sm backdrop-blur-sm",
        onClick && "cursor-pointer hover:border-slate-700 transition-colors",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "flex items-start justify-between gap-4 pb-4 border-b border-slate-800/80",
        className
      )}
    >
      <div>
        <h3 className="text-base font-semibold text-slate-100">{title}</h3>
        {subtitle && (
          <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}

export function CardContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={clsx("pt-4", className)}>{children}</div>;
}
