import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/** 卡片只在需要"这是一个独立对象"时用;列表行、面板内容不套卡片。 */
export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-line bg-surface shadow-sm", className)}
      {...rest}
    />
  );
}
