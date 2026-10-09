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
import { ApplicationRail } from "@/components/application-rail";
import { InboxToolbar } from "@/components/inbox-toolbar";
import { SearchBox } from "@/components/search-box";

function folderOf(value: string | null): FolderKey {
  return FOLDER_ORDER.includes(value as FolderKey) ? (value as FolderKey) : "all";
}

/** 页面只排版:哪个组件放哪儿。颜色、边框、圆角全在组件里(ADR-0002 第三条)。 */
export default function InboxPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [replyingFor, setReplyingFor] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [commandError, setCommandError] = useState<{ scope: string; message: string }>();
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
  const scope = `${mailbox.address}:${id ?? ""}`;
  const replying = replyingFor === scope;
  const organize = async () => {
    if (!selected || organizing) return;
    setOrganizing(true); setCommandError(undefined);
    try { setCommandError({ scope, message: await organizeThread(selected.id, selected.deleted_at ? "restore" : "trash") }); }
    catch (e) { setCommandError({ scope, message: e instanceof Error ? e.message : String(e) }); }
    finally { setOrganizing(false); }
  };
  const syncNow = async () => {
    setCommandError(undefined);
    try { setCommandError({ scope, message: await sync() }); }
    catch (e) { setCommandError({ scope, message: e instanceof Error ? e.message : String(e) }); }
  };

  return (
    <AppShell
      rail={<ApplicationRail leads={mailbox.tasks.includes("leads")} />}
      searchControl={<SearchBox placeholder="搜索当前视图 · 公司、型号、主题" value={query} onChange={setQuery} />}
      toolbar={<><InboxToolbar thread={selected} syncing={syncing} onSync={() => void syncNow()}
        replying={replying} onReply={() => setReplyingFor(replying ? "" : scope)}
        assistantOpen={assistantOpen} onAssistant={() => setAssistantOpen(value => !value)}
        busy={organizing} onOrganize={() => void organize()} />
        {commandError?.scope === scope && commandError.message && <p role="alert" className="mail-command-error">{commandError.message}</p>}</>}
      customerInitiallyCollapsed
      modelControl={mailbox.address && <ModelSelector mailbox={mailbox.address} load={modelSelection} save={setModelSelection} />}
      sidebar={<Sidebar foldersOnly counts={countFolders(threads)} activeFolder={folder} inInbox mailbox={mailbox} mailboxes={mailboxes} onMailboxChange={async address => {
        if (address === mailbox.address) return;
        navigate(`/${search}`);
        setAssistantOpen(false);
        setReplyingFor(""); setQuery(""); setCommandError(undefined);
        await selectMailbox(address);
      }} />}
      list={<ThreadList threads={visible} folder={folder} search={search} query={query} loading={loading} error={error} />}
      detail={
        selected ? (
          <ThreadDetail
            key={`${mailbox.address}:${selected.id}`}
            thread={selected}
            toolbarActions
            mailboxAddress={mailbox.address}
            replyControl={{ open: replying, onChange: open => setReplyingFor(open ? scope : "") }}
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
