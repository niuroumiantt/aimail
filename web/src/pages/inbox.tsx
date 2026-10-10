import { RefreshCw } from "lucide-react";
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
import { useMailFolders } from "@/data/mail-folders";
import { MailFolderTree, MoveToFolder } from "@/components/mail-folder-tree";
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
  const [forwardingFor, setForwardingFor] = useState("");
  const [replyingFor, setReplyingFor] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<{ mailbox: string; message: string }>();
  const [commandError, setCommandError] = useState<{ scope: string; message: string }>();
  const folder = folderOf(params.get("f"));
  const customFolder = params.get("cf");
  const search = customFolder ? `?cf=${encodeURIComponent(customFolder)}` : folder === "all" ? "" : `?f=${folder}`;
  const { loading, error, threads, details, openThread, mailbox, mailboxes, selectMailbox, user, setUser, latestDraft, makeDraft, send, attachmentText, attachmentFile, getMessageTranslation, translateMessage, sync, syncing, analyzeThread, organizeThread, assistant, askAssistant, clearAssistant, customerContext, refreshCustomerContext, modelSelection, setModelSelection } =
    useData();
  const folders = useMailFolders();
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

  const visible = threads.filter(t => customFolder ? !t.deleted_at && folders.data.assignments[t.id] === customFolder : inFolder(t, folder));
  const selected = id ? (details[id] ?? threads.find((t) => t.id === id)) : undefined;
  const scope = `${mailbox.address}:${id ?? ""}`;
  const replying = replyingFor === scope;
  const forwarding = forwardingFor === scope;
  const organize = async () => {
    if (!selected || organizing) return;
    setOrganizing(true); setCommandError(undefined);
    try { setCommandError({ scope, message: await organizeThread(selected.id, selected.deleted_at ? "restore" : "trash") }); }
    catch (e) { setCommandError({ scope, message: e instanceof Error ? e.message : String(e) }); }
    finally { setOrganizing(false); }
  };
  const syncNow = async () => {
    setSyncNotice(undefined);
    try { setSyncNotice({ mailbox: mailbox.address, message: await sync() }); }
    catch (e) { setSyncNotice({ mailbox: mailbox.address, message: e instanceof Error ? e.message : String(e) }); }
  };

  return (
    <AppShell
      rail={<ApplicationRail leads={mailbox.tasks.includes("leads")} />}
      searchControl={<SearchBox placeholder="搜索当前视图 · 公司、型号、主题" value={query} onChange={setQuery} />}
      toolbar={selected && <><InboxToolbar thread={selected}
        replying={replying} onReply={() => { setForwardingFor(""); setReplyingFor(replying ? "" : scope); }}
        forwarding={forwarding} onForward={() => { setReplyingFor(""); setForwardingFor(forwarding ? "" : scope); }}
        folderControl={<MoveToFolder key={scope} controller={folders} threadId={selected.id} />}
        assistantOpen={assistantOpen} onAssistant={() => setAssistantOpen(value => !value)}
        busy={organizing} onOrganize={() => void organize()} />
        {commandError?.scope === scope && commandError.message && <p role="alert" className="mail-command-error">{commandError.message}</p>}</>}
      customerInitiallyCollapsed
      modelControl={mailbox.address && <ModelSelector mailbox={mailbox.address} load={modelSelection} save={setModelSelection} />}
      sidebar={<Sidebar personalFolders={<MailFolderTree key={`${mailbox.address}:${user}`} controller={folders} />} customFolderActive={Boolean(customFolder)} foldersOnly counts={countFolders(threads)} activeFolder={folder} inInbox mailbox={mailbox} mailboxes={mailboxes} onMailboxChange={async address => {
        if (address === mailbox.address) return;
        navigate("/");
        setAssistantOpen(false);
        setForwardingFor(""); setReplyingFor(""); setQuery(""); setCommandError(undefined);
        await selectMailbox(address);
      }} />}
      list={<ThreadList title={customFolder ? folders.data.items.find(f => f.id === customFolder)?.name || "自建文件夹" : undefined} threads={visible} folder={folder} search={search} query={query} loading={loading} error={error}
        headerControl={<button type="button" className="mail-list-sync mail-icon-button" aria-label={syncing ? "正在同步邮箱" : "同步邮箱"} title="同步当前邮箱" disabled={syncing} onClick={() => void syncNow()}><RefreshCw size={16} className={syncing ? "animate-spin" : ""} /></button>}
        notice={syncNotice?.mailbox === mailbox.address ? syncNotice.message : undefined} />}
      detail={
        selected ? (
          <ThreadDetail
            key={`${mailbox.address}:${selected.id}`}
            thread={selected}
            toolbarActions
            mailboxAddress={mailbox.address}
            forwardControl={{ open: forwarding, onChange: open => { if (open) setReplyingFor(""); setForwardingFor(open ? scope : ""); } }}
            replyControl={{ open: replying, onChange: open => setReplyingFor(open ? scope : "") }}
            backSearch={search}
            reply={selected.deleted_at ? undefined : reply}
            onAttachment={attachmentText}
            onAttachmentFile={attachmentFile}
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
      onFullscreen={() => setAssistantOpen(false)}
      readerKey={`${mailbox.address}:${id ?? ""}`}
      showDetail={Boolean(selected)}
      customer={selected ? <CustomerWorkspace thread={selected} mailbox={mailbox.address} revision={`${selected.updated_at}:${selected.scale}:${selected.deleted_at ?? ""}`} load={customerContext} refresh={refreshCustomerContext} /> : undefined}
    />
  );
}
