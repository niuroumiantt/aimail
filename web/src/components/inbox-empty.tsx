import { EmptyState } from "./empty-state";

const GHOST = ["w-2/3", "w-1/2", "w-3/5", "w-2/5", "w-1/2"];

/** 右侧没选中线程时:淡淡铺一张"读数卡"的骨架,提示这里会出现什么。 */
export function InboxEmpty({ count }: { count: number }) {
  return (
    <EmptyState
      title={count > 0 ? "从左边选一封询盘" : "收件箱是空的"}
      subtitle={
        count > 0
          ? "右边会出现 AI 读数、数字核对和整封往来。用 ↑ ↓ 在列表里移动,Enter 打开。"
          : "新邮件从 sales@ 进来后会出现在这里。"
      }
      ghost={
        <div className="mx-auto mt-16 grid max-w-xl gap-4 px-6">
          <div className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-3 h-4 w-24 rounded-sm bg-surface-3" />
            {GHOST.map((w, i) => (
              <div key={i} className={`mb-2 h-3 rounded-sm bg-surface-3 ${w}`} />
            ))}
          </div>
          <div className="rounded-lg border border-line bg-surface p-4">
            {GHOST.slice(0, 3).map((w, i) => (
              <div key={i} className={`mb-2 h-3 rounded-sm bg-surface-3 ${w}`} />
            ))}
          </div>
        </div>
      }
    />
  );
}
