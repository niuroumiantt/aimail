import { ArrowLeft, Reply, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import type { AttachmentText, Thread } from "@/data/types";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { CustomerHistory } from "./customer-history";
import { FOLDER_LABEL } from "./folders";
import { MessageView, type TranslationHandlers } from "./message";
import { Pill } from "./pill";
import { ReadingCard } from "./reading-card";
import { ReplyComposer, type ReplyHandlers } from "./reply-composer";
import { Tip } from "./tip";
import { MailLabel } from "./mail-label";
import { fullTime } from "@/lib/text";
import "@/tokens/conversation-timeline.css";

/** 线程页。有 reply(接上了数据源)才能回信;页面按线程 id 加 key,切线程时回信框状态归零。 */
export function ThreadDetail({
  thread,
  backSearch,
  reply,
  onAttachment,
  onAttachmentFile,
  onGetTranslation,
  onTranslate,
  assistantOpen = false,
  onAssistant,
  onAnalyze,
  onOrganize,
  externalContext = false,
  draftScope,
  toolbarActions = false,
  replyControl,
  mailboxAddress,
}: TranslationHandlers & {
  thread: Thread;
  backSearch: string;
  reply?: ReplyHandlers;
  /** 点附件时取它的文字;没有就只显示名字 */
  onAttachment?: (attachmentId: string) => Promise<AttachmentText>;
  onAttachmentFile?: (attachmentId: string) => Promise<Blob>;
  assistantOpen?: boolean;
  onAssistant?: () => void;
  onAnalyze?: () => Promise<string>;
  onOrganize?: (action: "trash" | "restore") => Promise<string>;
  externalContext?: boolean;
  draftScope?: string;
  toolbarActions?: boolean;
  replyControl?: { open: boolean; onChange: (open: boolean) => void };
  mailboxAddress?: string;
}) {
  const replyPanel = useRef<HTMLDivElement>(null);
  const [localReplying, setLocalReplying] = useState(false);
  const replying = replyControl?.open ?? localReplying;
  const setReplying = (open: boolean) => replyControl ? replyControl.onChange(open) : setLocalReplying(open);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [organizeError, setOrganizeError] = useState("");
  const { hash } = useLocation();
  useEffect(() => {
    if (replying) replyPanel.current?.scrollIntoView?.({ block: "start" });
  }, [replying]);
  useEffect(() => {
    const match = /^#mail-(\d+)$/.exec(hash);
    if (match && thread.messages.some(message => message.id === match[1])) document.getElementById(`mail-${match[1]}`)?.scrollIntoView({ block: "center" });
  }, [hash, thread.messages]);
  const organize = async () => {
    if (!onOrganize || organizing) return;
    setOrganizing(true);
    setOrganizeError("");
    try { setOrganizeError(await onOrganize(thread.deleted_at ? "restore" : "trash")); }
    catch (e) { setOrganizeError(e instanceof Error ? e.message : String(e)); }
    finally { setOrganizing(false); }
  };
  return (
    <>
      <header className="mail-detail-header">
        <div className="mail-detail-title">
        <Link
          to={{ pathname: "/", search: backSearch }}
          aria-label="返回列表"
          className="mail-icon-button md:hidden"
        >
          <ArrowLeft size={18} />
        </Link>
          <h2>{thread.subject}</h2>
        </div>
        {(!toolbarActions || thread.messages.length === 0) && <div className="mail-detail-meta">
          <Avatar name={thread.contact} size="sm" muted />
          <p>
            <span className="font-medium text-ink">{thread.contact}</span>
            {thread.company !== thread.contact && <span>{thread.company}</span>}
            {thread.region && <span className="text-ink-3">·</span>}
            {thread.region && <span>{thread.region}</span>}
            <span className="text-ink-3">·</span>
            <span>{thread.email}</span>
            {thread.history?.length === 0 && <span>第一次来信</span>}
          </p>
        </div>}
        <div className="mail-detail-actions">
          <MailLabel thread={thread} />
          {toolbarActions && thread.history?.length === 0 && <span className="mail-muted">第一次来信</span>}
          {["quote", "replied"].includes(thread.folder) && <Pill tone="neutral" dot>
            {FOLDER_LABEL[thread.folder]}
          </Pill>}
          <span className="mail-detail-action-spacer" />
          {!toolbarActions && <>
          {!thread.deleted_at && import.meta.env.VITE_DATA_SOURCE === "api" && <Link className="mail-detail-assignment" to={`/followups/${thread.id}`}>分配</Link>}
          {onAssistant && <Button size="sm" variant={assistantOpen ? "soft" : "outline"} aria-pressed={assistantOpen} icon={<Sparkles size={14} />} onClick={onAssistant}>AI 阅读</Button>}
          <Tip label={reply ? "回复这封信" : "回复(要接上服务端)"}>
            <Button
              size="sm"
              variant={replying ? "soft" : "outline"}
              icon={<Reply size={14} strokeWidth={2} />}
              disabled={!reply}
              aria-pressed={replying}
              onClick={() => setReplying(!replying)}
            >
              回复
            </Button>
          </Tip>
          {onOrganize && <Tip label={thread.deleted_at ? "恢复到收件列表" : "整条会话移入 Aimail 回收站，邮箱原件保留"}>
            <Button size="sm" variant="outline" disabled={organizing} onClick={() => void organize()}
              icon={thread.deleted_at ? <RotateCcw size={14} /> : <Trash2 size={14} />}>
              {organizing ? "处理中…" : thread.deleted_at ? "恢复" : "删除"}
            </Button>
          </Tip>}
          </>}
        </div>
      </header>

      <div className="mail-detail-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="mail-detail-body">
          {thread.deleted_at && <div role="status" className="rounded-md border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
            已移入 Aimail 回收站，可点击“恢复”。邮箱服务商中的原件仍保留；此会话收到新回复时会重新出现在收件列表。
          </div>}
          {organizeError && <p role="alert" className="text-sm text-danger-text">{organizeError}</p>}
          {!externalContext && thread.history && thread.history.length > 0 && <CustomerHistory items={thread.history} />}
          {!externalContext && <ReadingCard reading={thread.reading} analyzing={analyzing} error={analysisError} onAnalyze={onAnalyze && !thread.deleted_at ? async () => { setAnalyzing(true); setAnalysisError(""); const message = await onAnalyze(); setAnalysisError(message); setAnalyzing(false); } : undefined} />}
          <section className="mail-conversation" aria-label="邮件时间线" data-single={thread.messages.length === 1}>
            {thread.messages.length > 1 ? <details className="mail-conversation-index" open={thread.messages.length <= 6}>
              <summary className="mail-conversation-heading"><strong>往来时间线 <span>{thread.messages.length}</span></strong><span>从早到晚 · 点击定位邮件</span></summary>
              <nav aria-label="往来邮件时间导航"><ol>{thread.messages.map(m => <li key={m.id}>
                <a href={`#mail-${m.id}`} aria-current={hash === `#mail-${m.id}` ? "location" : undefined}>
                  <time dateTime={m.sent_at}>{fullTime(m.sent_at)}</time><span title={m.from_name}>{m.from_name}</span><small>{m.direction === "out" ? "我方回复" : "来信"}</small>
                </a>
              </li>)}</ol></nav>
            </details> : null}
            <ol className="mail-conversation-timeline">
              {thread.messages.map((m, index) => (
                <li key={m.id} className="mail-conversation-entry" data-direction={m.direction} data-tone={index % 2 ? "alternate" : "default"}>
                  <div className="mail-conversation-caption"><span className="mail-conversation-dot" aria-hidden>{index + 1}</span><span>{m.direction === "out" ? "我方回复" : "来信"}</span>{index === thread.messages.length - 1 && <span className="mail-conversation-latest">最新往来</span>}</div>
                  <MessageView message={m} onAttachment={onAttachment} onAttachmentFile={onAttachmentFile}
                    mailboxAddress={mailboxAddress}
                    onGetTranslation={onGetTranslation} onTranslate={onTranslate} />
                </li>
              ))}
            </ol>
          </section>
          {replying && reply && (
            <div ref={replyPanel}><ReplyComposer thread={thread} reply={reply} cacheKey={draftScope} onClose={() => setReplying(false)} /></div>
          )}
        </div>
      </div>
    </>
  );
}
