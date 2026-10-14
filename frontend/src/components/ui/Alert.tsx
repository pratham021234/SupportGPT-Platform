import React from "react";
import { clsx } from "clsx";
import { AlertCircle, CheckCircle2, Info, AlertTriangle } from "lucide-react";

export interface AlertProps {
  variant?: "info" | "success" | "warning" | "danger";
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Alert({
  variant = "info",
  title,
  children,
  className,
}: AlertProps) {
  const variantStyles = {
    info: "bg-sky-950/40 border-sky-800/60 text-sky-200",
    success: "bg-emerald-950/40 border-emerald-800/60 text-emerald-200",
    warning: "bg-amber-950/40 border-amber-800/60 text-amber-200",
    danger: "bg-rose-950/40 border-rose-800/60 text-rose-200",
  };

  const icons = {
    info: <Info className="w-5 h-5 text-sky-400 flex-shrink-0" />,
    success: <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />,
    danger: <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0" />,
  };

  return (
    <div
      className={clsx(
        "flex items-start gap-3 p-4 rounded-xl border text-sm",
        variantStyles[variant],
        className
      )}
    >
      {icons[variant]}
      <div className="flex-1">
        {title && <h4 className="font-semibold mb-1 text-slate-100">{title}</h4>}
        <div className="leading-relaxed text-slate-300">{children}</div>
      </div>
    </div>
  );
}
