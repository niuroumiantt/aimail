import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { AppShell } from "@/components/app-shell";
import { AiReadingPanel } from "@/components/ai-reading-panel";
import { countFolders, FOLDER_ORDER, inFolder, type FolderKey } from "@/components/folders";
import { InboxEmpty } from "@/components/inbox-empty";
import type { ReplyHandlers } from "@/components/reply-composer";
import { Sidebar } from "@/components/sidebar";
import { ThreadDetail } from "@/components/thread-detail";
import { ThreadList } from "@/components/thread-list";
import { useData } from "@/data/provider";
import { CustomerWorkspace } from "@/components/customer-workspace";
import { ModelSelector } from "@/components/model-selector";

function folderOf(value: string | null): FolderKey {
  return FOLDER_ORDER.includes(value as FolderKey) ? (value as FolderKey) : "all";
}

/** 页面只排版:哪个组件放哪儿。颜色、边框、圆角全在组件里(ADR-0002 第三条)。 */
export default function InboxPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const folder = folderOf(params.get("f"));
  const search = folder === "all" ? "" : `?f=${folder}`;
  const { loading, error, threads, details, openThread, mailbox, mailboxes, selectMailbox, user, setUser, latestDraft, makeDraft, send, attachmentText, getMessageTranslation, translateMessage, sync, syncing, analyzeThread, organizeThread, assistant, askAssistant, clearAssistant, customerContext, refreshCustomerContext, modelSelection, setModelSelection } =
    useData();
  const loadAssistant = useCallback(() => assistant(), [assistant]);
  const submitAssistant = useCallback((question: string) => askAssistant(question), [askAssistant]);
  const clearAssistantTurns = useCallback(() => clearAssistant(), [clearAssistant]);
  // 列表只有摘要行;信件与客户历史在详情里。列表刷新(发信、确认之后)时详情也跟着刷
  useEffect(() => {
    if (id) void openThread(id);
  }, [id, openThread, threads]);
  const canDraft = mailbox.tasks.includes("draft");
  const reply = useMemo<ReplyHandlers>(
    () => ({ user, onSetUser: setUser, canDraft, latestDraft, makeDraft, send }),
    [user, setUser, canDraft, latestDraft, makeDraft, send],
  );

  const visible = threads.filter(t => inFolder(t, folder));
  const selected = id ? (details[id] ?? threads.find((t) => t.id === id)) : undefined;

  return (
    <AppShell
      modelControl={mailbox.address && <ModelSelector mailbox={mailbox.address} load={modelSelection} save={setModelSelection} />}
      sidebar={<Sidebar counts={countFolders(threads)} activeFolder={folder} inInbox mailbox={mailbox} mailboxes={mailboxes} onMailboxChange={async address => {
        if (address === mailbox.address) return;
        navigate(`/${search}`);
        setAssistantOpen(false);
        await selectMailbox(address);
      }} onSync={sync} syncing={syncing} />}
      list={<ThreadList threads={visible} folder={folder} search={search} loading={loading} error={error} />}
      detail={
        selected ? (
          <ThreadDetail
            key={`${mailbox.address}:${selected.id}`}
            thread={selected}
            backSearch={search}
            reply={selected.deleted_at ? undefined : reply}
            onAttachment={attachmentText}
            onGetTranslation={getMessageTranslation}
            onTranslate={translateMessage}
            assistantOpen={assistantOpen}
            onAssistant={() => setAssistantOpen((value) => !value)}
            onAnalyze={() => analyzeThread(selected.id)}
            onOrganize={action => organizeThread(selected.id, action)}
            externalContext
            draftScope={`${mailbox.address}:${user}:${selected.id}`}
          />
        ) : (
          <InboxEmpty count={visible.length} loading={loading} error={error} />
        )
      }
      assistant={<AiReadingPanel open={assistantOpen} mailbox={mailbox.address} load={loadAssistant} ask={submitAssistant} clear={clearAssistantTurns} onClose={() => setAssistantOpen(false)} onCitation={(threadId) => { navigate(`/t/${threadId}`); void openThread(threadId); }} />}
      assistantOpen={assistantOpen}
      readerKey={`${mailbox.address}:${id ?? ""}`}
      showDetail={Boolean(selected)}
      customer={selected ? <CustomerWorkspace thread={selected} mailbox={mailbox.address} revision={`${selected.updated_at}:${selected.scale}:${selected.deleted_at ?? ""}`} load={customerContext} refresh={refreshCustomerContext} /> : undefined}
    />
  );
}
