import { ArrowLeft, Archive, Reply, Sparkles, Tag } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
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

/** 线程页。有 reply(接上了数据源)才能回信;页面按线程 id 加 key,切线程时回信框状态归零。 */
export function ThreadDetail({
  thread,
  backSearch,
  reply,
  onAttachment,
  assistantOpen = false,
  onAssistant,
  onAnalyze,
}: {
  thread: Thread;
  backSearch: string;
  reply?: ReplyHandlers;
  /** 点附件时取它的文字;没有就只显示名字 */
  onAttachment?: (attachmentId: string) => Promise<AttachmentText>;
  assistantOpen?: boolean;
  onAssistant?: () => void;
  onAnalyze?: () => Promise<string>;
}) {
  const [replying, setReplying] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
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
        <Avatar name={thread.contact} size="lg" muted={thread.folder === "invalid"} />
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
        <div className="flex basis-full shrink-0 items-center justify-end gap-1.5 md:basis-auto">
          {import.meta.env.VITE_DATA_SOURCE === "api" && <Link to={`/followups/${thread.id}`}>分配 / 转交</Link>}
          <Pill tone={FOLDER_TONE[thread.folder]} dot>
            {FOLDER_LABEL[thread.folder]}
          </Pill>
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
          <Tip label="改标签">
            <Button size="sm" variant="ghost" aria-label="改标签" icon={<Tag size={15} strokeWidth={1.75} />} />
          </Tip>
          <Tip label="归档">
            <Button size="sm" variant="ghost" aria-label="归档" icon={<Archive size={15} strokeWidth={1.75} />} />
          </Tip>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-3xl gap-5 px-5 py-5">
          {thread.history && thread.history.length > 0 && <CustomerHistory items={thread.history} />}
          <ReadingCard reading={thread.reading} analyzing={analyzing} error={analysisError} onAnalyze={onAnalyze ? async () => { setAnalyzing(true); setAnalysisError(""); const message = await onAnalyze(); setAnalysisError(message); setAnalyzing(false); } : undefined} />
          {thread.messages.map((m) => (
            <MessageView key={m.id} message={m} onAttachment={onAttachment} />
          ))}
          {replying && reply && (
            <ReplyComposer thread={thread} reply={reply} onClose={() => setReplying(false)} />
          )}
        </div>
      </div>
    </>
  );
}
