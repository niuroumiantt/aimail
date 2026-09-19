import { hash, initials } from "@/lib/text";
import { cn } from "@/lib/cn";

/* 头像色从五个淡底里按名字哈希固定选一个;同一个人永远同一个颜色。
   圆角按尺寸的 25% 走(6 / 8 / 12),小头像更方,大头像更圆——这是从 Chatwoot 学来的比例。 */
const TINTS = [
  "bg-brand-wash text-brand-deep",
  "bg-ok-wash text-ok-text",
  "bg-warn-wash text-warn-text",
  "bg-danger-wash text-danger-text",
  "bg-surface-3 text-ink-2",
];

const SIZES = {
  sm: "size-6 rounded-sm text-2xs",
  md: "size-8 rounded-md text-xs",
  lg: "size-10 rounded-lg text-sm",
} as const;

export function Avatar({
  name,
  size = "md",
  muted = false,
  className,
}: {
  name: string;
  size?: keyof typeof SIZES;
  /** 无效线程等场景:灰掉 */
  muted?: boolean;
  className?: string;
}) {
  const tint = muted ? TINTS[4] : TINTS[hash(name) % TINTS.length];
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center font-semibold",
        SIZES[size],
        tint,
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
