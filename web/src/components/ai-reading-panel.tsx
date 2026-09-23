import { Eraser, ExternalLink, Search, Send, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { AssistantState } from "@/data/types";
import { Button } from "./button";

const PROMPTS = [
  "哪些邮件是客户发来的询价？",
  "哪些客户提到了 Supermicro 或 GPU 服务器？",
  "有哪些客户明确提出了数量或交期？",
];

export function AiReadingPanel({
  open,
  mailbox,
  load,
  ask,
  clear,
  onClose,
  onCitation,
}: {
  open: boolean;
  mailbox: string;
  load: () => Promise<AssistantState>;
  ask: (question: string) => Promise<AssistantState>;
  clear: () => Promise<AssistantState>;
  onClose: () => void;
  onCitation: (threadId: string) => void;
}) {
  const [state, setState] = useState<AssistantState>();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    void load()
      .then((value) => { if (alive) { setState(value); setError(""); } })
      .catch((reason) => alive && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => { alive = false; };
  }, [open, mailbox, load]);

  useEffect(() => { end.current?.scrollIntoView?.({ block: "nearest" }); }, [state?.turns.length]);

  async function submit(value = question) {
    const text = value.trim();
    if (!text || busy || !state?.configured) return;
    setBusy(true);
    setError("");
    try {
      setState(await ask(text));
      setQuestion("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function clearTurns() {
    if (busy) return;
    setBusy(true);
    try { setState(await clear()); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  if (!open) return null;
  return (
    <aside className="fixed inset-0 z-40 flex min-w-0 flex-col border-l border-line bg-canvas shadow-xl xl:static xl:z-auto xl:w-100 xl:shrink-0 xl:shadow-none" aria-label="AI 阅读">
      <header className="flex h-14 items-center gap-3 border-b border-line px-4">
        <span className="grid size-8 place-items-center rounded-md bg-brand-wash text-brand-text"><Sparkles size={16} /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-ink">AI 阅读</h2>
          <p className="truncate font-mono text-2xs text-ink-3" title={mailbox}>{mailbox}</p>
        </div>
        <Button variant="ghost" size="sm" aria-label="清空 AI 阅读对话" disabled={busy || !state?.turns.length} icon={<Eraser size={14} />} onClick={() => void clearTurns()} />
        <Button variant="ghost" size="sm" aria-label="收起 AI 阅读" icon={<X size={16} />} onClick={onClose} />
      </header>

      <div className="border-b border-line bg-brand-wash/50 px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-ink"><Search size={13} className="text-brand-text" />当前邮箱范围</div>
        <p className="mt-1 text-2xs leading-relaxed text-ink-2">最多阅读最新 60 封已同步邮件；答案必须附原文引用，不含附件。</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {!state && !error && <p className="text-sm text-ink-2">正在连接 AI 阅读…</p>}
        {error && <div role="alert" className="mb-4 rounded-md border border-danger-line bg-danger-wash px-3 py-2 text-xs text-danger-text">{error}</div>}
        {state && !state.configured && (
          <div className="rounded-lg border border-warn-line bg-warn-wash p-4">
            <p className="font-medium text-warn-text">AI 接口尚未配置</p>
            <p className="mt-1 text-xs leading-relaxed text-warn-text">{state.reason}</p>
            <p className="mt-3 text-2xs text-ink-2">邮件和双邮箱功能不受影响；配置前不会伪造 AI 结果。</p>
          </div>
        )}
        {state?.configured && !state.turns.length && (
          <div className="py-5">
            <p className="text-base font-semibold text-ink">把散落的往来，<br />连成可核对的答案。</p>
            <p className="mt-2 text-xs leading-relaxed text-ink-2">跨话题查找询盘、型号、数量和交期，每条结论都可回到邮件原文。</p>
            <div className="mt-5 grid gap-2">
              {PROMPTS.map((prompt) => <button key={prompt} type="button" onClick={() => setQuestion(prompt)} className="rounded-lg border border-line bg-surface px-3 py-3 text-left text-xs text-ink transition-colors hover:border-brand-line hover:bg-brand-wash">{prompt}</button>)}
            </div>
          </div>
        )}
        <div className="grid gap-5">
          {state?.turns.map((turn) => (
            <section key={turn.id} className="grid gap-3">
              <p className="ml-8 rounded-lg bg-surface-3 px-3 py-2 text-sm text-ink">{turn.question}</p>
              {turn.status === "failed" ? <p role="alert" className="text-xs text-danger-text">{turn.error}</p> : (
                <div className="rounded-lg border border-line bg-surface p-3 shadow-sm">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-text"><Sparkles size={13} />邮箱助手 <span className="ml-auto font-normal text-2xs text-ink-3">待人工核对</span></div>
                  {!turn.findings?.length && <p className="mt-3 text-xs leading-relaxed text-ink-2">本次提供的正文中没有找到足够依据。</p>}
                  {turn.findings?.map((finding, index) => (
                    <div key={`${finding.source_id}-${index}`} className="mt-3 border-t border-line pt-3 first:border-0 first:pt-1">
                      {!!finding.unverified.length && <p className="mb-2 rounded bg-warn-wash px-2 py-1 text-2xs text-warn-text">数字待核对：{finding.unverified.join("、")}</p>}
                      <p className="text-xs leading-relaxed text-ink">{finding.text}</p>
                      <button type="button" onClick={() => onCitation(String(finding.thread_id))} className="mt-2 inline-flex items-center gap-1 text-2xs font-medium text-brand-text hover:underline">[{index + 1}] {finding.subject}<ExternalLink size={11} /></button>
                      <details className="mt-2 text-2xs text-ink-2"><summary className="cursor-pointer">查看原文依据</summary><blockquote className="mt-2 border-l-2 border-brand-line pl-2 leading-relaxed">{finding.quote}</blockquote></details>
                    </div>
                  ))}
                  <p className="mt-3 border-t border-line pt-2 font-mono text-2xs leading-relaxed text-ink-3">{turn.model} · {turn.task_version}<br />覆盖 {turn.scope?.included ?? 0} / {turn.scope?.total ?? 0} 封 · 截断 {turn.scope?.truncated ?? 0} 封</p>
                </div>
              )}
            </section>
          ))}
          <div ref={end} />
        </div>
      </div>

      <form className="border-t border-line bg-surface p-3" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <textarea aria-label="向 AI 阅读提问" value={question} onChange={(event) => setQuestion(event.target.value)} disabled={!state?.configured || busy} maxLength={2000} rows={3} placeholder="问整个邮箱，例如：哪些客户在询价 B300？" className="w-full resize-none rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-brand-line disabled:opacity-60" />
        <div className="mt-2 flex items-center justify-between"><span className="text-2xs text-ink-3">只读分析 · 不会发送邮件</span><Button type="submit" size="sm" disabled={!question.trim() || !state?.configured || busy} icon={<Send size={13} />}>{busy ? "阅读中…" : "提问"}</Button></div>
      </form>
    </aside>
  );
}
