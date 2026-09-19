import { useEffect, useMemo } from "react";
import { useParams, useSearchParams } from "react-router";
import { AppShell } from "@/components/app-shell";
import { FOLDER_ORDER, type FolderKey } from "@/components/folders";
import { InboxEmpty } from "@/components/inbox-empty";
import type { ReplyHandlers } from "@/components/reply-composer";
import { Sidebar } from "@/components/sidebar";
import { ThreadDetail } from "@/components/thread-detail";
import { ThreadList } from "@/components/thread-list";
import { useData } from "@/data/provider";
import type { Thread } from "@/data/types";

function folderOf(value: string | null): FolderKey {
  return FOLDER_ORDER.includes(value as FolderKey) ? (value as FolderKey) : "all";
}

function countBy(threads: Thread[]): Record<FolderKey, number> {
  const counts = { all: threads.length, inbox: 0, quote: 0, replied: 0, invalid: 0 };
  for (const t of threads) counts[t.folder] += 1;
  return counts;
}

/** 页面只排版:哪个组件放哪儿。颜色、边框、圆角全在组件里(ADR-0002 第三条)。 */
export default function InboxPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const folder = folderOf(params.get("f"));
  const search = folder === "all" ? "" : `?f=${folder}`;
  const { threads, details, openThread, user, setUser, latestDraft, makeDraft, send } = useData();
  // 列表只有摘要行;信件与客户历史在详情里。列表刷新(发信、确认之后)时详情也跟着刷
  useEffect(() => {
    if (id) void openThread(id);
  }, [id, openThread, threads]);
  const reply = useMemo<ReplyHandlers>(
    () => ({ user, onSetUser: setUser, latestDraft, makeDraft, send }),
    [user, setUser, latestDraft, makeDraft, send],
  );

  const visible = folder === "all" ? threads : threads.filter((t) => t.folder === folder);
  const selected = id ? (details[id] ?? threads.find((t) => t.id === id)) : undefined;

  return (
    <AppShell
      sidebar={<Sidebar counts={countBy(threads)} activeFolder={folder} inInbox />}
      list={<ThreadList threads={visible} folder={folder} search={search} />}
      detail={
        selected ? (
          <ThreadDetail key={selected.id} thread={selected} backSearch={search} reply={reply} />
        ) : (
          <InboxEmpty count={visible.length} />
        )
      }
      showDetail={Boolean(selected)}
    />
  );
}
