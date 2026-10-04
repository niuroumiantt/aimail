import { ArrowLeft, Reply, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
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

/** 线程页。有 reply(接上了数据源)才能回信;页面按线程 id 加 key,切线程时回信框状态归零。 */
export function ThreadDetail({
  thread,
  backSearch,
  reply,
  onAttachment,
  onGetTranslation,
  onTranslate,
  assistantOpen = false,
  onAssistant,
  onAnalyze,
  onOrganize,
  externalContext = false,
  draftScope,
}: TranslationHandlers & {
  thread: Thread;
  backSearch: string;
  reply?: ReplyHandlers;
  /** 点附件时取它的文字;没有就只显示名字 */
  onAttachment?: (attachmentId: string) => Promise<AttachmentText>;
  assistantOpen?: boolean;
  onAssistant?: () => void;
  onAnalyze?: () => Promise<string>;
  onOrganize?: (action: "trash" | "restore") => Promise<string>;
  externalContext?: boolean;
  draftScope?: string;
}) {
  const [replying, setReplying] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [organizeError, setOrganizeError] = useState("");
  const { hash } = useLocation();
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
        <div className="mail-detail-meta">
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
        </div>
        <div className="mail-detail-actions">
          <MailLabel thread={thread} />
          {["quote", "replied"].includes(thread.folder) && <Pill tone="neutral" dot>
            {FOLDER_LABEL[thread.folder]}
          </Pill>}
          <span className="mail-detail-action-spacer" />
          {!thread.deleted_at && import.meta.env.VITE_DATA_SOURCE === "api" && <Link className="mail-detail-assignment" to={`/followups/${thread.id}`}>分配</Link>}
          {onAssistant && <Button size="sm" variant={assistantOpen ? "soft" : "outline"} aria-pressed={assistantOpen} icon={<Sparkles size={14} />} onClick={onAssistant}>AI 阅读</Button>}
          <Tip label={reply ? "回复这封信" : "回复(要接上服务端)"}>
            <Button
              size="sm"
              variant={replying ? "soft" : "outline"}
              icon={<Reply size={14} strokeWidth={2} />}
              disabled={!reply}
              aria-pressed={replying}
              onClick={() => setReplying((v) => !v)}
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
          {thread.messages.map((m) => (
            <MessageView key={m.id} message={m} onAttachment={onAttachment}
              onGetTranslation={onGetTranslation} onTranslate={onTranslate} />
          ))}
          {replying && reply && (
            <ReplyComposer thread={thread} reply={reply} cacheKey={draftScope} onClose={() => setReplying(false)} />
          )}
        </div>
      </div>
    </>
  );
}
