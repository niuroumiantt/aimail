import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Tone = "neutral" | "brand" | "ok" | "warn" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-ink-2",
  brand: "bg-brand-wash text-brand-deep",
  ok: "bg-ok-wash text-ok-text",
  warn: "bg-warn-wash text-warn-text",
  danger: "bg-danger-wash text-danger-text",
};

const DOTS: Record<Tone, string> = {
  neutral: "bg-ink-3",
  brand: "bg-brand",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
};

/** 小标签。状态用颜色 + 可选的点表达,一眼能分。 */
export function Pill({
  tone = "neutral",
  dot = false,
  mono = false,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  /** 型号、编号这类用等宽 */
  mono?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-sm px-1.5 text-2xs font-medium leading-none",
        mono && "font-mono",
        TONES[tone],
        className,
      )}
    >
      {dot && <span className={cn("size-1.5 rounded-full", DOTS[tone])} />}
      {children}
    </span>
  );
}
