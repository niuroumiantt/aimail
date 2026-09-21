import { ArrowDown, ArrowUp, ArrowUpRight, ChevronRight, FileSpreadsheet, GripHorizontal, Layers, Mail, Sparkles } from "lucide-react";
import { useState, type ReactNode } from "react";

export type TopicMail = { id: string; date: string; sender: string; subject: string; body: string; outgoing?: boolean; attachment?: string };
type TopicItem = { subject: string; contact: string; body: string; request: string; attachment: string; old: string; quantity: string; unit: string; product: string; time: string };

/** Fictional thread history for the design study, not generated or retrieved mail. */
export function topicMails(item: TopicItem, index: number): TopicMail[] {
  const day = item.time === "昨天" ? "09-18" : item.time.includes(":") ? "09-19" : item.time.replace("9/", "09-");
  const latest: TopicMail = { id: "latest", date: `${day} ${item.time.includes(":") ? item.time : "10:00"}`, sender: item.contact, subject: `Re: ${item.subject.replace(/^Re: /, "")}`, body: `${index === 2 ? "Larry，你好，" : "Hi Larry,"}\n\n${item.body}\n\n${item.request}\n\n${index === 2 ? "谢谢，" : "Best regards,"}\n${item.contact}`, attachment: item.attachment };
  if (index === 0) return [
    { id: "initial", date: "09-12 10:25", sender: item.contact, subject: "RFQ: 48 × 2U servers for Helsinki DC", body: "Hi Larry,\n\nWe are planning an expansion of our Helsinki data center and need 48 units of 2U rack servers. Please quote dual Xeon E5-2680 v4, 128 GB ECC and four 3.84 TB SSDs per server. Refurbished units are acceptable if tested.\n\nPlease include CIF Helsinki pricing and a 12-month warranty.\n\nBest regards,\nMikko", attachment: item.attachment },
    { id: "reply", date: "09-16 14:10", sender: "Larry", outgoing: true, subject: "Re: RFQ: 48 × 2U servers — configuration proposal", body: "Hi Mikko,\n\nWe have prepared a configuration proposal for 48 units based on your requirements. We are checking stock availability and shipping options for CIF Helsinki.\n\nCould you confirm your preferred delivery date? Final pricing and lead time are still pending.\n\nBest regards,\nLarry" }, latest,
  ];
  if (index === 1) return [
    { id: "initial", date: "09-15 11:20", sender: item.contact, subject: "RFQ: HGX H200 systems for Dubai", body: "Hi Larry,\n\nWe are planning a GPU cluster expansion in Dubai. We are considering HGX H200 systems. Could you help us confirm a suitable configuration?\n\nBest regards,\nOmar" },
    { id: "reply", date: "09-17 16:05", sender: "Larry", outgoing: true, subject: "Re: HGX H200 — quantity and delivery details", body: "Hi Omar,\n\nWe can review an eight-GPU HGX H200 configuration. Please confirm the number of systems, delivery address and preferred delivery date so we can prepare a quotation.\n\nBest regards,\nLarry" }, latest,
  ];
  return [latest];
}

export function TopicOverview({ mails, activeId, onRead, children, last, onMove, recap, customer }: {
  mails: TopicMail[]; activeId: string; onRead: (id: string) => void; children: ReactNode; last: boolean; onMove: () => void;
  recap: string;
  customer: { company: string; city: string; contact: string; email: string };
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  return <section className="ds-topic" aria-label="专题总览" draggable={false}>
    <header className="ds-topic-header" draggable onDragStart={event => { event.dataTransfer.setData("application/x-mail2leads-panel", "topic"); event.dataTransfer.effectAllowed = "move"; }} title="拖动标题栏，与邮件原文交换位置"><div><GripHorizontal size={13} /><span className="ds-topic-icon"><Layers size={16} /></span><strong>专题总览</strong><span className="ds-topic-badge">仅当前话题</span></div><button onClick={onMove} aria-label={last ? "将专题总览移至正文上方" : "将专题总览移至正文下方"}>{last ? <ArrowUp size={14} /> : <ArrowDown size={14} />}移动</button></header>
    <div className="ds-topic-provenance"><Sparkles size={13} /><span>综合本专题 {mails.length} 封邮件 · 最新总结</span><span>更新至 {mails.at(-1)?.date} · 示例</span></div>
    <div className="ds-topic-customer"><p><strong>{customer.company}</strong>，位于{customer.city.split(" · ").reverse().join(" · ")}。当前联系人为 <strong>{customer.contact}</strong>（职位未提供），公司联系邮箱 <a href={`mailto:${customer.email}`}>{customer.email}</a>。</p><div><span>本话题参与者</span>{[...new Set(mails.map(mail => mail.sender))].map(name => <span className="ds-participant" key={name}>{name}{name === "Larry" ? " · 我方" : " · 客户"}</span>)}</div></div>
    <p className="ds-topic-recap"><strong>话题总结</strong>{recap}</p>
    {children}
    <div className="ds-topic-timeline-heading"><strong>专题邮件 <span>{mails.length}</span></strong><span>时间正序 · 点标题展开原文</span></div>
    <ol className="ds-topic-timeline">{mails.map((mail, index) => {
      const isExpanded = expanded.includes(mail.id);
      return <li key={mail.id} className={activeId === mail.id ? "is-reading" : ""}>
        <button className="ds-timeline-row" aria-expanded={isExpanded} aria-controls={`topic-mail-${mail.id}`} onClick={() => { setExpanded(previous => isExpanded ? previous.filter(id => id !== mail.id) : [...previous, mail.id]); onRead(mail.id); }}>
          <time>{mail.date}</time><span className={`ds-timeline-direction ${mail.outgoing ? "is-outgoing" : ""}`}>{mail.outgoing ? "发" : "收"}</span><span className="ds-timeline-text"><strong>{mail.subject}</strong><small>{mail.sender}{index === mails.length - 1 ? " · 最新" : ""}</small></span><ChevronRight size={13} className={isExpanded ? "is-expanded" : ""} />
        </button>
        <div id={`topic-mail-${mail.id}`} hidden={!isExpanded} className="ds-timeline-expanded"><p>{mail.body}</p>{mail.attachment && <span><FileSpreadsheet size={13} />{mail.attachment}</span>}<button onClick={() => { onRead(mail.id); document.getElementById("topic-original")?.scrollIntoView({ block: "start", behavior: "smooth" }); }}>在邮件阅读区查看 <ArrowUpRight size={13} /></button></div>
      </li>;
    })}</ol>
    <footer className="ds-topic-footer"><span>AI 综合总结与邮件原文分开呈现 · 待人工核对</span><span><GripHorizontal size={12} />拖右下角调高度</span></footer>
  </section>;
}

export function TopicOriginal({ mail, onAttachment }: { mail: TopicMail; onAttachment: () => void }) {
  return <section className="ds-topic-original" id="topic-original" aria-label="邮件原文阅读区">
    <div className="ds-original-label" draggable onDragStart={event => { event.dataTransfer.setData("application/x-mail2leads-panel", "original"); event.dataTransfer.effectAllowed = "move"; }} title="拖动标题栏，与专题总览交换位置"><span><GripHorizontal size={13} /><Mail size={14} />邮件原文</span><span>当前阅读  ·  {mail.outgoing ? "我方发出" : "客户来信"}</span></div>
    <h3>{mail.subject}</h3>
    <div className="ds-original-meta"><strong>{mail.sender}</strong><span>{mail.outgoing ? "发给客户" : "发送至 sales@glocal.example"}</span><time>{mail.date}</time></div>
    <div className="ds-original-body">{mail.body}</div>
    {mail.attachment && <button className="ds-attachment" onClick={onAttachment}><span className="ds-file-icon"><FileSpreadsheet size={21} /></span><span><strong>{mail.attachment}</strong><small>XLSX · 示例附件</small></span><ArrowUpRight size={16} /></button>}
  </section>;
}
