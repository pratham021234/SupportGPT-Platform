import React from "react";
import { clsx } from "clsx";

export interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={clsx(
        "animate-pulse rounded-md bg-slate-800/80",
        className
      )}
    />
  );
}
