import type { ReactNode } from "react";

/** 空状态:把"有内容时长什么样"淡淡地铺在后面,前面压一层渐变和一句话。
 *  这是从 Chatwoot 的 EmptyStateLayout 学来的做法——不用插画也有画面。 */
export function EmptyState({
  title,
  subtitle,
  action,
  ghost,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
  ghost?: ReactNode;
}) {
  return (
    <section className="relative flex h-full min-h-72 w-full flex-col items-center justify-center overflow-hidden">
      {ghost && (
        <div aria-hidden className="pointer-events-none absolute inset-0 select-none opacity-40">
          {ghost}
        </div>
      )}
      <div className="relative flex w-full flex-col items-center gap-3 bg-linear-to-t from-canvas from-55% to-transparent px-6 pb-10 pt-24 text-center">
        <h2 className="text-base font-semibold text-ink text-balance">{title}</h2>
        <p className="max-w-sm text-sm text-ink-2 text-pretty">{subtitle}</p>
        {action && <div className="mt-1">{action}</div>}
      </div>
    </section>
  );
}
