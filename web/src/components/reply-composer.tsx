import { Ban, Reply, Send, Sparkles, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ReplyDraft, SendRequest, Thread } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime, replySubject } from "@/lib/text";
import { Button } from "./button";
import { NamePrompt } from "./name-prompt";
import { Pill } from "./pill";
import { Tip } from "./tip";

/** 模型在草稿里留给人的署名位。它还在,信就不该出门。 */
export const NAME_PLACEHOLDER = "[姓名]";

export type ReplyHandlers = {
  user: string;
  onSetUser: (name: string) => void;
  latestDraft: (threadId: string) => Promise<ReplyDraft | null>;
  makeDraft: (threadId: string) => Promise<ReplyDraft>;
  /** 返回错误文案;空串 = 发出去了 */
  send: (threadId: string, request: SendRequest) => Promise<string>;
};

/** 收件人框里的文本 → 地址列表。逗号、分号、空白都当分隔。 */
export function parseRecipients(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 发送前由代码裁决,不问模型:收件人和正文不能空;模型留的占位必须换成人的署名。 */
export function sendProblem(request: SendRequest): string {
  if (request.to.length === 0) return "还没有收件人";
  if (!request.body.trim()) return "正文是空的";
  if (request.body.includes(NAME_PLACEHOLDER)) return `正文里还有 ${NAME_PLACEHOLDER} 占位,换成你的署名再发`;
  return "";
}

function Field({
  id,
  label,
  value,
  onChange,
  mono,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  mono?: boolean;
}) {
  return (
    <label htmlFor={id} className="grid grid-cols-kv items-center gap-3 bg-surface px-4 py-1.5 text-sm">
      <span className="w-12 text-xs text-ink-2">{label}</span>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn("h-7 min-w-0 bg-transparent text-ink outline-none", mono && "font-mono text-xs")}
      />
    </label>
  );
}

/** 草稿的来历,压在正文上面:谁起的、哪些数字对不上、问了客户什么、占位换了没。 */
function DraftNote({ draft, hasPlaceholder }: { draft: ReplyDraft; hasPlaceholder: boolean }) {
  if (draft.status === "failed") {
    return (
      <div
        role="alert"
        data-testid="draft-failed"
        className="flex items-start gap-2 border-t border-line bg-danger-wash px-4 py-2.5 text-xs text-danger-text"
      >
        <Ban size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
        <span>
          模型没有起出草稿,这封请自己写。
          <span className="ml-1 font-mono">{draft.reason}</span>
        </span>
      </div>
    );
  }
  return (
    <div data-testid="draft-note" className="grid gap-2 border-t border-line bg-surface-2 px-4 py-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles size={13} strokeWidth={2} className="text-brand-text" />
        <span className="text-ink">草稿来自</span>
        <Tip label={`${draft.model} · ${draft.task_version} · ${fullTime(draft.produced_at)}`}>
          <span data-testid="attribution" className="font-mono text-2xs text-ink-2">
            {draft.model}
            <span className="text-ink-3"> · </span>
            {draft.task_version}
          </span>
        </Tip>
        <Pill mono>{draft.language}</Pill>
        {hasPlaceholder && (
          <span className="ml-auto inline-flex items-center gap-1 text-warn-text">
            <TriangleAlert size={13} strokeWidth={2} />把 {NAME_PLACEHOLDER} 换成你的署名
          </span>
        )}
      </div>
      {draft.unverified.length > 0 && (
        <div role="alert" className="rounded-md border border-warn-line bg-warn-wash px-3 py-2 text-warn-text">
          <p className="font-semibold">草稿里这些数字在来信里找不到,发之前先核对</p>
          <p className="mt-1 font-mono">{draft.unverified.join(" · ")}</p>
        </div>
      )}
      {draft.open_questions.length > 0 && <p className="text-ink-2">草稿向客户问了:{draft.open_questions.join(";")}</p>}
    </div>
  );
}

/** 回信框。模型只起草;改和发都是人。发之前的硬规矩在 sendProblem 里,是代码不是提示词。 */
export function ReplyComposer({
  thread,
  reply,
  onClose,
}: {
  thread: Thread;
  reply: ReplyHandlers;
  onClose: () => void;
}) {
  const [to, setTo] = useState(thread.email);
  const [subject, setSubject] = useState(replySubject(thread.subject));
  const [body, setBody] = useState("");
  const [draft, setDraft] = useState<ReplyDraft | null>(null);
  const [busy, setBusy] = useState<"" | "draft" | "send">("");
  const [problem, setProblem] = useState("");
  const root = useRef<HTMLElement>(null);
  const restored = useRef(false);

  // 打开时把上次的草稿找回来:真模型要几十秒,不能因为切了一下线程就丢
  useEffect(() => {
    if (restored.current) return;
    let alive = true;
    reply
      .latestDraft(thread.id)
      .then((d) => {
        if (!alive) return;
        restored.current = true;
        if (d && d.status === "ok") {
          setDraft(d);
          setBody((current) => current || d.body);
          setSubject((current) => d.subject || current);
        }
      })
      .catch(() => {
        /* 找不回来就从空白开始 */
      });
    root.current?.scrollIntoView?.({ block: "nearest" });
    return () => {
      alive = false;
    };
  }, [reply, thread.id]);

  const draftNow = async () => {
    setBusy("draft");
    setProblem("");
    try {
      const d = await reply.makeDraft(thread.id);
      setDraft(d);
      if (d.status === "ok") {
        setBody(d.body);
        if (d.subject) setSubject(d.subject);
      }
    } catch (e) {
      setProblem(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };

  const sendNow = async () => {
    const request: SendRequest = {
      to: parseRecipients(to),
      subject: subject.trim(),
      body,
      draft_id: draft?.status === "ok" ? draft.id : undefined,
    };
    const early = sendProblem(request);
    if (early) {
      setProblem(early);
      return;
    }
    setBusy("send");
    setProblem("");
    const err = await reply.send(thread.id, request);
    setBusy("");
    if (err) setProblem(err);
    else onClose();
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void sendNow();
    }
  };

  const hasPlaceholder = body.includes(NAME_PLACEHOLDER);
  const canAct = Boolean(reply.user) && !busy;

  return (
    <section
      ref={root}
      aria-label="回信"
      data-testid="composer"
      className="overflow-hidden rounded-lg border border-brand-line bg-surface shadow-sm"
    >
      <header className="flex items-center gap-2 border-b border-line bg-brand-wash/40 px-4 py-2.5">
        <span className="inline-flex size-6 items-center justify-center rounded-sm bg-brand-wash text-brand-text">
          <Reply size={14} strokeWidth={2} />
        </span>
        <h3 className="text-sm font-semibold text-ink">回信</h3>
        {reply.user && (
          <span className="text-xs text-ink-2">
            以 <span className="font-medium text-ink">{reply.user}</span> 的名义发出
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          aria-label="关闭回信框"
          className="ml-auto"
          icon={<X size={15} strokeWidth={2} />}
          onClick={onClose}
        />
      </header>

      {!reply.user && (
        <div className="border-b border-line p-3">
          <NamePrompt why="发出去的信署你的名字。先写上你的名字:" user={reply.user} onSetUser={reply.onSetUser} />
        </div>
      )}

      <div className="grid gap-px bg-line">
        <Field id="reply-to" label="收件人" value={to} onChange={setTo} mono />
        <Field id="reply-subject" label="主题" value={subject} onChange={setSubject} />
      </div>

      {draft && <DraftNote draft={draft} hasPlaceholder={hasPlaceholder} />}

      <textarea
        id="reply-body"
        aria-label="正文"
        rows={10}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={onKey}
        placeholder="写给客户的话。也可以先让 AI 起草,再改成你的口吻。"
        className="block w-full resize-y border-t border-line bg-surface px-4 py-3 font-sans text-sm leading-relaxed text-ink outline-none placeholder:text-ink-3"
      />

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
        <Button
          variant="soft"
          size="sm"
          icon={<Sparkles size={14} strokeWidth={2} />}
          onClick={draftNow}
          disabled={!canAct}
        >
          {busy === "draft" ? "起草中…" : draft ? "重新起草" : "AI 起草"}
        </Button>
        <span className="text-xs text-ink-3">草稿只是建议,发出去的每个字都算你说的。</span>
        <span className="ml-auto flex items-center gap-2">
          {problem && (
            <span role="alert" className="text-xs text-danger-text">
              {problem}
            </span>
          )}
          <Tip label="⌘ Enter 也能发">
            <Button
              variant="solid"
              size="sm"
              icon={<Send size={14} strokeWidth={2} />}
              onClick={sendNow}
              disabled={!canAct}
            >
              {busy === "send" ? "发送中…" : "发送"}
            </Button>
          </Tip>
        </span>
      </footer>
    </section>
  );
}
