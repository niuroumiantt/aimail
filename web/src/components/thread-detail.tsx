import { ArrowLeft, Reply, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import type { AttachmentText, Thread } from "@/data/types";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { CustomerHistory } from "./customer-history";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { MessageView } from "./message";
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
  assistantOpen = false,
  onAssistant,
  onAnalyze,
  onOrganize,
  externalContext = false,
  draftScope,
}: {
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
      <header className="flex flex-wrap items-start gap-3 border-b border-line bg-surface px-5 py-4">
        <Link
          to={{ pathname: "/", search: backSearch }}
          aria-label="返回列表"
          className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface-2 md:hidden"
        >
          <ArrowLeft size={16} strokeWidth={2} />
        </Link>
        <Avatar name={thread.contact} size="lg" muted />
        <div className="min-w-0 flex-1 basis-48">
          <h2 className="text-base font-semibold leading-snug text-ink text-balance">{thread.subject}</h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-2">
            <span className="font-medium text-ink">{thread.contact}</span>
            <span>{thread.company}</span>
            {thread.region && <span className="text-ink-3">·</span>}
            {thread.region && <span>{thread.region}</span>}
            <span className="text-ink-3">·</span>
            <span className="font-mono">{thread.email}</span>
          </p>
        </div>
        <div className="flex basis-full shrink-0 flex-wrap items-center justify-end gap-1.5 md:basis-auto">
          {!thread.deleted_at && import.meta.env.VITE_DATA_SOURCE === "api" && <Link to={`/followups/${thread.id}`}>分配 / 转交</Link>}
          <MailLabel thread={thread} />
          {["quote", "replied"].includes(thread.folder) && <Pill tone={FOLDER_TONE[thread.folder]} dot>
            {FOLDER_LABEL[thread.folder]}
          </Pill>}
          {thread.history?.length === 0 && <Pill tone="brand">第一次来信</Pill>}
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

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-3xl gap-5 px-5 py-5">
          {thread.deleted_at && <div role="status" className="rounded-md border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
            已移入 Aimail 回收站，可点击“恢复”。邮箱服务商中的原件仍保留；此会话收到新回复时会重新出现在收件列表。
          </div>}
          {organizeError && <p role="alert" className="text-sm text-danger-text">{organizeError}</p>}
          {!externalContext && thread.history && thread.history.length > 0 && <CustomerHistory items={thread.history} />}
          {!externalContext && <ReadingCard reading={thread.reading} analyzing={analyzing} error={analysisError} onAnalyze={onAnalyze && !thread.deleted_at ? async () => { setAnalyzing(true); setAnalysisError(""); const message = await onAnalyze(); setAnalysisError(message); setAnalyzing(false); } : undefined} />}
          {thread.messages.map((m) => (
            <MessageView key={m.id} message={m} onAttachment={onAttachment} />
          ))}
          {replying && reply && (
            <ReplyComposer thread={thread} reply={reply} cacheKey={draftScope} onClose={() => setReplying(false)} />
          )}
        </div>
      </div>
    </>
  );
}
