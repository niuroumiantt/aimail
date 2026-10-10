import { Forward, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Thread } from "@/data/types";
import { fullTime } from "@/lib/text";
import { Button } from "./button";
import { MessageView } from "./message";
import { NamePrompt } from "./name-prompt";
import { parseRecipients, type ReplyHandlers } from "./reply-composer";
import "@/tokens/mail-folders.css";

type Draft = { to: string; subject: string; body: string; messageId: string; attachments: boolean };
const drafts = new Map<string, Draft>();

export function ForwardComposer({ thread, reply, cacheKey, onClose }: {
  thread: Thread; reply: ReplyHandlers; cacheKey?: string; onClose: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => (cacheKey && drafts.get(cacheKey)) || {
    to: "", subject: /^fwd?:/i.test(thread.subject) ? thread.subject : `Fwd: ${thread.subject}`,
    body: "", messageId: thread.messages.at(-1)?.id ?? "", attachments: true,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const root = useRef<HTMLElement>(null);
  useEffect(() => { root.current?.scrollIntoView?.({ block: "start" }); }, []);
  useEffect(() => { if (cacheKey) drafts.set(cacheKey, draft); }, [cacheKey, draft]);
  const original = thread.messages.find(m => m.id === draft.messageId);
  const patch = (value: Partial<Draft>) => setDraft(current => ({ ...current, ...value }));
  const send = async () => {
    if (busy || !reply.user) return;
    const to = parseRecipients(draft.to);
    if (!to.length || to.some(value => !/^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$/.test(value))) {
      setError("请填写有效的收件邮箱，多个地址用逗号分隔"); return;
    }
    if (!original) { setError("请先选择要转发的邮件"); return; }
    setBusy(true); setError("");
    try {
      const problem = await reply.send(thread.id, { to, subject: draft.subject, body: draft.body,
        forward_message_id: original.id, include_attachments: draft.attachments });
      if (problem) setError(problem);
      else { if (cacheKey) drafts.delete(cacheKey); onClose(); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  return <section ref={root} aria-label="转发邮件" className="mail-forward-composer">
    <header><Forward size={18} /><strong>转发</strong><span>原文和内嵌图片随邮件转发</span>
      <Button size="sm" variant="ghost" aria-label="关闭转发框" disabled={busy} icon={<X size={16} />} onClick={onClose} />
    </header>
    {!reply.user && <NamePrompt why="请先填写你的名字" user={reply.user} onSetUser={reply.onSetUser} />}
    <fieldset disabled={busy}>
      <label>转发哪封邮件<select value={draft.messageId} onChange={e => patch({ messageId: e.target.value })}>
        {thread.messages.map(m => <option key={m.id} value={m.id}>{fullTime(m.sent_at)} · {m.from_name || m.from_email}</option>)}
      </select></label>
      <label>收件人<input autoFocus value={draft.to} placeholder="输入收件邮箱，多个地址用逗号分隔" onChange={e => patch({ to: e.target.value })} /></label>
      <label>主题<input value={draft.subject} onChange={e => patch({ subject: e.target.value })} /></label>
      <label>补充说明<textarea rows={4} value={draft.body} placeholder="可以在原文前补充说明（选填）" onChange={e => patch({ body: e.target.value })} /></label>
      <label className="mail-forward-attachments"><input type="checkbox" checked={draft.attachments} onChange={e => patch({ attachments: e.target.checked })} />包含原邮件附件
        <small>{original?.attachments?.map(a => a.name).join("、") || "这封邮件没有独立附件"}</small></label>
    </fieldset>
    {error && <p role="alert" className="mail-folder-error">{error}</p>}
    <footer><span>以 {reply.user || "你的个人邮箱"} 的发件身份发送</span><Button icon={<Send size={16} />} disabled={busy || !reply.user || !original} onClick={() => void send()}>{busy ? "正在发送…" : "发送转发"}</Button></footer>
    {original && <details><summary>查看转发原文</summary><MessageView message={original} /></details>}
  </section>;
}
