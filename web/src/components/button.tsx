import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "solid" | "soft" | "outline" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  solid: "bg-brand text-on-brand hover:bg-brand-2",
  soft: "bg-brand-wash text-brand-text hover:bg-brand-wash-2",
  outline: "border border-line bg-surface text-ink hover:bg-surface-2",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger: "bg-danger text-on-brand hover:brightness-95",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 gap-1 px-2.5 text-xs",
  md: "h-8 gap-1.5 px-3 text-sm",
};

export function Button({
  variant = "outline",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        !children && (size === "sm" ? "w-7 px-0" : "w-8 px-0"),
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}
