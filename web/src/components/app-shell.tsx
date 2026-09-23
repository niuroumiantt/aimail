import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** 三栏壳:侧栏 | 列表 | 详情;或 侧栏 | 主区。手机上列表与详情二选一,由路由决定。 */
export function AppShell({
  sidebar,
  list,
  detail,
  main,
  assistant,
  assistantOpen = false,
  showDetail = false,
}: {
  sidebar: ReactNode;
  list?: ReactNode;
  detail?: ReactNode;
  main?: ReactNode;
  assistant?: ReactNode;
  assistantOpen?: boolean;
  showDetail?: boolean;
}) {
  return (
    <div className="flex h-full min-h-0 w-full bg-canvas">
      <div className={cn("hidden md:flex", assistantOpen && "md:hidden 2xl:flex")}>{sidebar}</div>
      {main ? (
        <main className="min-w-0 flex-1 overflow-y-auto">{main}</main>
      ) : (
        <>
          <section
            aria-label="列表"
            className={cn(
              "w-full shrink-0 flex-col border-r border-line bg-surface md:flex md:w-88",
              showDetail ? "hidden" : "flex",
            )}
          >
            {list}
          </section>
          <main className={cn("min-w-0 flex-1 flex-col md:flex", showDetail ? "flex" : "hidden")}>
            {detail}
          </main>
          {assistant}
        </>
      )}
    </div>
  );
}
