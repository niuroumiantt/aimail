import type { Thread } from "@/data/types";
import { EmptyState } from "./empty-state";
import { FOLDER_LABEL, type FolderKey } from "./folders";
import { SearchBox } from "./search-box";
import { ThreadRow } from "./thread-row";

export function ThreadList({
  threads,
  folder,
  search,
}: {
  threads: Thread[];
  folder: FolderKey;
  search: string;
}) {
  return (
    <>
      <header className="grid gap-3 border-b border-line px-4 pb-3 pt-4">
        <div className="flex items-baseline gap-2">
          <h2 className="text-base font-semibold text-ink">{FOLDER_LABEL[folder]}</h2>
          <span className="font-mono text-xs tabular-nums text-ink-2">{threads.length}</span>
        </div>
        <SearchBox />
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {threads.length === 0 ? (
          <EmptyState title="这个分组是空的" subtitle="新来的询盘会按读数结果自动落到对应分组。" />
        ) : (
          threads.map((t) => <ThreadRow key={t.id} thread={t} search={search} />)
        )}
      </div>
    </>
  );
}
