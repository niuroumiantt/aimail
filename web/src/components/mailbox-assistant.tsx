import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, ArrowUpRight, Check, ChevronDown, Globe2, Mail, MessageSquare, Plus, Search, Sparkles, X, Eraser, History } from "lucide-react";
import { recordDesignAudit } from "@/lib/design-audit";

type MailExample = { company: string; subject: string; body: string; request: string; product: string; model: string; quantity: string; old: string; unit: string; contact: string };
type QuestionKind = "inquiries" | "changes" | "pending" | "search";
type Turn = { id: number; question: string; scope: string; summary: string; sources: { index: number; title: string; detail: string; quote: string }[] };
const prompts: { title: string; subtitle: string; kind: QuestionKind }[] = [
  { title: "找出所有询价邮件", subtitle: "跨邮件归纳需求，逐条查看出处", kind: "inquiries" },
  { title: "哪些客户修改了数量？", subtitle: "把前后变化放在一起看", kind: "changes" },
  { title: "还有哪些询盘待确认？", subtitle: "根据当前原型的人工确认状态整理", kind: "pending" },
];

/** Local design demonstration only. No model, network retrieval, or mailbox permissions implied. */
export function MailboxAssistant({ open, examples, selected, confirmed, onClose, onNavigate }: {
  open: boolean; examples: MailExample[]; selected: number; confirmed: number[];
  onClose: () => void; onNavigate: (index: number) => void;
}) {
  const [scope, setScope] = useState("all");
  const [question, setQuestion] = useState("");
  const [allTurns, setTurns] = useState<Turn[]>([]);
  const [clearedThrough, setClearedThrough] = useState(0);
  const [auditStatus, setAuditStatus] = useState("");
  const [clearing, setClearing] = useState(false);
  const turns = useMemo(() => allTurns.filter(turn => turn.id > clearedThrough), [allTurns, clearedThrough]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  async function clearDisplay(newConversation = false) {
    const boundary = nextId.current;
    setClearing(true);
    try {
      await recordDesignAudit(newConversation ? "assistant.new_conversation" : "assistant.clear_display", { turns: allTurns, scope, selected });
      setClearedThrough(boundary);
      if (newConversation) { setQuestion(""); setTurns([]); }
      setAuditStatus("已清屏 · 本机服务端记录保留（演示身份）");
      inputRef.current?.focus();
    } catch { setAuditStatus("记录写入失败，未清屏。请重试。"); }
    finally { setClearing(false); }
  }
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  useEffect(() => { if (open) bottomRef.current?.scrollIntoView({ block: "nearest" }); }, [turns, open]);

  function ask(text: string, kind: QuestionKind = "search") {
    if (!text.trim() || clearing) return;
    void recordDesignAudit("assistant.question", { question: text, scope, selected }).catch(() => setAuditStatus("提问记录写入失败；当前为本地演示"));
    const fixedPrompt = prompts.find(prompt => prompt.title === text.trim());
    const mode = fixedPrompt?.kind ?? kind;
    const pool = examples.map((mail, index) => ({ ...mail, index })).filter(mail => scope === "all" || mail.index === selected);
    const results = pool.filter(mail => {
      if (mode === "changes") return !!mail.old;
      if (mode === "pending") return !confirmed.includes(mail.index);
      if (mode === "inquiries") return true;
      const needle = text.trim().toLowerCase();
      return `${mail.company} ${mail.subject} ${mail.body} ${mail.request} ${mail.model} ${mail.product}`.toLowerCase().includes(needle);
    });
    const summary = mode === "changes"
      ? `这份示例中有 ${results.length} 条数量变更。确认需求时，注意邮件中的最新数量与旧附件是否一致。`
      : mode === "pending" ? `当前范围内有 ${results.length} 条询盘尚未人工确认。这里的“待确认”不等于尚未回复。`
      : mode === "inquiries" ? `当前范围内共有 ${results.length} 条示例询盘，涉及以下客户与需求。数量按各自单位列出，不合并相加。`
      : results.length ? `按“${text.trim()}”在示例邮件中查到 ${results.length} 条匹配。以下为示例字段与原文，未调用模型分析。`
      : "示例邮件中没有这个词的直接匹配。本原型尚未接入自然语言分析；可以输入 H200、DDR5、Aurora 等关键词，或试试下方的示例问题。";
    setTurns(previous => [...previous, { id: ++nextId.current, question: text.trim(), scope: scope === "all" ? `全部邮箱 · 1 个示例邮箱 · ${pool.length} 条询盘` : `仅此询盘 · ${examples[selected].company}`, summary, sources: results.map(mail => ({ index: mail.index, title: mail.company, detail: mode === "changes" ? `${mail.product} · ${mail.old} → ${mail.quantity} ${mail.unit}` : `${mail.product} · ${mail.quantity} ${mail.unit}`, quote: mail.body })) }]);
    setQuestion("");
  }

  return <aside className="ds-assistant" hidden={!open} aria-label="问邮箱" onKeyDown={event => { event.stopPropagation(); if (event.key === "Escape") onClose(); }}>
    <header className="ds-assistant-header"><span><Sparkles size={17} /><strong>问邮箱</strong></span><div><button aria-label="清空当前显示" disabled={clearing || !turns.length} onClick={() => void clearDisplay()}><Eraser size={15} />清屏</button><button aria-label="开始新对话" disabled={clearing} onClick={() => void clearDisplay(true)}><Plus size={16} />新对话</button><button aria-label="收起问邮箱" onClick={onClose}><X size={18} /></button></div></header>
    {auditStatus && <div role="status" className={`ds-audit-status ${auditStatus.includes("失败") ? "ds-audit-error" : ""}`}>{auditStatus}</div>}
    {clearedThrough > 0 && allTurns.some(turn => turn.id <= clearedThrough) && <button className="ds-show-cleared" onClick={() => { setClearedThrough(0); setAuditStatus("已恢复当前会话的显示"); }}><History size={13} />查看已清屏的对话</button>}
    <div className="ds-assistant-scope"><Globe2 size={14} /><label htmlFor="mail-assistant-scope">阅读范围</label><select id="mail-assistant-scope" value={scope} onChange={event => setScope(event.target.value)}><option value="all">全部邮箱</option><option value="current">仅此询盘</option></select><ChevronDown size={12} /></div>
    <div className="ds-assistant-coverage"><span className="ds-status-dot" />{scope === "all" ? `sales@ · 1 个示例邮箱 / ${examples.length} 条询盘` : examples[selected].company}<span>交互演示</span></div>
    <div className="ds-assistant-scroll">
      {!turns.length ? <div className="ds-assistant-welcome"><span className="ds-assistant-symbol"><MessageSquare size={26} strokeWidth={1.4} /></span><div className="ds-eyebrow">YOUR MAIL, CONNECTED</div><h2>把散落的往来，<br />连成清楚的答案。</h2><p>查找询盘、梳理变化、回看依据。<br />范围由你选择，不随左侧选信改变。</p><div className="ds-assistant-prompts">{prompts.map(prompt => <button key={prompt.kind} onClick={() => ask(prompt.title, prompt.kind)}><div><strong>{prompt.title}</strong><small>{prompt.subtitle}</small></div><ArrowUpRight size={15} /></button>)}</div><div className="ds-assistant-disclosure"><Search size={14} /><span>当前使用固定示例与关键词匹配。<br />正式接入后，只检索你有权访问的邮箱。</span></div></div> : <div className="ds-assistant-turns">{turns.map(turn => <section className="ds-assistant-turn" key={turn.id}><div className="ds-assistant-question">{turn.question}</div><div className="ds-assistant-answer"><div className="ds-answer-byline"><Sparkles size={14} /><span>邮箱助手</span><small>示例结果</small></div><p className="ds-answer-scope">{turn.scope}</p><p className="ds-answer-summary">{turn.summary}</p><div className="ds-answer-sources">{turn.sources.map((source, rank) => <div className="ds-answer-source" key={source.index}><button onClick={() => onNavigate(source.index)} aria-label={`查看来源：${source.title}`}><span className="ds-citation-number">{rank + 1}</span><div><strong>{source.title}</strong><span>{source.detail}</span></div><ArrowUpRight size={14} /></button><details><summary>邮件原文摘录</summary><blockquote>{source.quote}</blockquote></details></div>)}</div>{turn.sources.length > 0 && <div className="ds-answer-footnote"><Check size={12} />引用可点回邮件 · 结果仅覆盖上方示例范围</div>}</div></section>)}<div className="ds-assistant-followups">{prompts.map(prompt => <button key={prompt.kind} onClick={() => ask(prompt.title, prompt.kind)}>{prompt.title}<ArrowUpRight size={12} /></button>)}</div></div>}
      <div ref={bottomRef} />
    </div>
    <form className="ds-assistant-composer" onSubmit={event => { event.preventDefault(); ask(question); }}>
      <div className="ds-assistant-context"><Mail size={13} /><span>{scope === "all" ? "跨邮件查找，不附带当前选中的邮件" : `仅查询：${examples[selected].company}`}</span></div>
      <textarea ref={inputRef} aria-label="向邮箱提问" placeholder="问问整个邮箱，或输入客户、型号…" value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(question); } }} />
      <div className="ds-assistant-send"><span>示例问答 · 不会修改或发送邮件</span><button type="submit" aria-label="提交邮箱问题" disabled={!question.trim()}><ArrowUp size={18} /></button></div>
    </form>
  </aside>;
}
