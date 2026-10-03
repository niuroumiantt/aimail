import type { Thread } from "@/data/types";
import { useNavigate } from "react-router";
import { EmptyState } from "./empty-state";
import { FOLDER_LABEL, FOLDER_ORDER, type FolderKey } from "./folders";
import { SearchBox } from "./search-box";
import { ThreadRow } from "./thread-row";

export function ThreadList({
  threads,
  folder,
  search,
  loading = false,
  error,
}: {
  threads: Thread[];
  folder: FolderKey;
  search: string;
  loading?: boolean;
  error?: string;
}) {
  const navigate = useNavigate();
  return (
    <>
      <header className="grid gap-3 border-b border-line px-4 pb-3 pt-4">
        <div className="flex items-baseline gap-2">
          <h2 className="text-base font-semibold text-ink">{FOLDER_LABEL[folder]}</h2>
          <span className="font-mono text-xs tabular-nums text-ink-2">{threads.length}</span>
        </div>
        <select aria-label="邮件分组" value={folder} className="h-8 min-w-0 rounded-md border border-line bg-surface px-2 text-sm text-ink md:hidden"
          onChange={e => navigate(e.target.value === "all" ? "/" : `/?f=${e.target.value}`)}>
          {FOLDER_ORDER.map(key => <option key={key} value={key}>{FOLDER_LABEL[key]}</option>)}
        </select>
        <SearchBox />
      </header>
      {error && <p role="alert" className="border-b border-line px-4 py-3 text-xs text-danger-text">加载失败：{error}。请刷新页面重试。</p>}
      <div aria-busy={loading} className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <p role="status" className="px-4 py-6 text-sm text-ink-2">正在加载邮件…</p>
        ) : threads.length === 0 && !error ? (
          <EmptyState title="这个分组是空的" subtitle={folder === "trash" ? "删除的会话会出现在这里，可以恢复。" : "邮件保留在全部列表，潜在线索会突出显示。"} />
        ) : (
          threads.map((t) => <ThreadRow key={t.id} thread={t} search={search} />)
        )}
      </div>
    </>
  );
}
