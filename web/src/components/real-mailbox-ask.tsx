import { useEffect, useRef, useState } from "react";
import { Alert, Button, Empty, Input, Popconfirm, Tag } from "antd";
import { Eraser, Send, Sparkles, X } from "lucide-react";

type Finding = { text: string; quote: string; source_id: number; thread_id: number; subject: string; unverified: string[] };
type Turn = { id: string; question: string; status: string; error?: string; findings?: Finding[]; model?: string; task_version?: string; produced_at?: string; scope?: { total: number; included: number; truncated: number } };
async function api(path = "", body?: object) {
  const response = await fetch(`/__localmail/assistant${path}`, { method: body ? "POST" : "GET", headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw Error(data.detail || "问邮箱服务未连接");
  return data;
}

export function RealMailboxAsk({ open, onClose, onCitation, onBusy }: { open: boolean; onClose: () => void; onCitation: (thread: number, message: number) => void; onBusy: (busy: boolean) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [clearing, setClearing] = useState(false);
  const sending = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open && !busy) return;
    let alive = true, fetching = false;
    async function refresh() {
      if (fetching) return;
      fetching = true;
      try { const data = await api(); if (alive) { setTurns(data.turns); setBusy(data.job.status === "running"); setError(""); } }
      catch (e) { if (alive) setError(e instanceof Error ? e.message : String(e)); }
      finally { fetching = false; }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => { alive = false; window.clearInterval(timer); };
  }, [open, busy]);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [turns.length]);

  async function submit() {
    if (!question.trim() || busy || sending.current || clearing) return;
    sending.current = true; setBusy(true); setError(""); onBusy(true);
    try { await api("", { question: question.trim() }); setQuestion(""); const data = await api(); setTurns(data.turns); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); onBusy(false); }
    finally { sending.current = false; }
  }
  async function clear() {
    setClearing(true);
    try { await api("/clear", {}); setTurns([]); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setClearing(false); }
  }
  return <aside className="mw-ask" hidden={!open} aria-label="问邮箱">
    <header><strong><Sparkles size={15} />问邮箱</strong><div><Popconfirm title="清空当前对话界面？" description="后台问题、回答和清屏记录均保留。" onConfirm={clear} disabled={busy || !turns.length}><Button type="text" aria-label="清空对话界面" disabled={busy || !turns.length} loading={clearing} icon={<Eraser size={14} />} /></Popconfirm><Button type="text" aria-label="关闭问邮箱" icon={<X size={15} />} onClick={onClose} /></div></header>
    <div className="mw-ask-scope"><Tag color="blue">跨话题</Tag>本地已同步邮件<p>不随左侧选中的邮件改变范围 · 正文片段，不含附件</p></div>
    <div className="mw-ask-scroll">{error && <Alert type="error" title={error} showIcon />}{!turns.length && !busy && <div className="mw-ask-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="从邮件往来中寻找答案" /><p>问题会通过本机 API 分析，答案附原文引用。</p>{["哪些邮件是客户发来的询价？", "哪些邮件提到了 B300？", "有哪些明确提出交期要求的客户？"].map(q => <Button block key={q} onClick={() => setQuestion(q)}>{q}</Button>)}</div>}{turns.map(t => <section className="mw-ask-turn" key={t.id}><div className="mw-ask-question">{t.question}</div>{t.status === "failed" ? <Alert type="error" title={t.error || "回答失败，请重试"} showIcon /> : t.status === "running" ? <p role="status">正在阅读正文并核对引用…</p> : <><div className="mw-ask-answer-label"><Sparkles size={13} />回答 · 待人工核对</div>{!t.findings?.length && <p>本次提供的正文片段中没有找到足够依据。不能据此断定其他邮件中不存在。</p>}{t.findings?.map((f, i) => <div className="mw-ask-finding" key={i}>{!!f.unverified.length && <Alert type="warning" title={`数字待核对：${f.unverified.join("、")}`} />}<p>{f.text}</p><Button type="link" className="mw-ask-citation" onClick={() => onCitation(f.thread_id, f.source_id)}>[{i + 1}] {f.subject} ↗</Button><details><summary>查看原文依据</summary><blockquote>{f.quote}</blockquote></details></div>)}<div className="mw-ask-provenance">{t.model} · {t.task_version}<br />{t.produced_at && new Date(t.produced_at).toLocaleString("zh-CN")}<br />本次提供 {t.scope?.included} / {t.scope?.total} 封本地邮件 · {t.scope?.truncated} 封正文截断 · 不含附件</div></>}</section>)}{busy && !turns.some(t => t.status === "running") && <p role="status">后台任务进行中，请稍候…</p>}<div ref={end} /></div>
    <form className="mw-ask-compose" onSubmit={e => { e.preventDefault(); void submit(); }}><Input.TextArea aria-label="向邮箱提问" placeholder="跨话题提问，例如：哪些客户在询价 B300？" maxLength={2000} autoSize={{ minRows: 3, maxRows: 6 }} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void submit(); } }} /><div><span>清屏不删除记录 · ⌘/Ctrl Enter</span><Button type="primary" htmlType="submit" aria-label="发送问题" icon={<Send size={14} />} loading={busy} disabled={!question.trim() || busy || clearing} /></div></form>
  </aside>;
}
