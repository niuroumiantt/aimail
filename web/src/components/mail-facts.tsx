import { useEffect, useState } from "react";
import { Button, Popover, Tag } from "antd";

export type MailExtraction = { status: string; facts: { key: string; value: string; quote: string }[]; model: string; task_version: string; produced_at: string; source_id: number; coverage: string; reason: string };
const rows = [
  [["公司", "company"], ["联系人", "contact"], ["邮箱", "email"], ["国家 / 城市", "country", "city"], ["职位", "title"]],
  [["产品 / 型号", "product", "model"], ["数量", "quantity"], ["价格 / 币种", "price", "currency"], ["交期", "delivery"], ["贸易 / 付款", "trade", "payment"], ["客户要求", "request"], ["我方承诺", "commitment"], ["下一步", "next_action"]],
];

export function MailFacts({ messageId, threadId, initial }: { messageId: number; threadId: number; initial?: MailExtraction }) {
  const [data, setData] = useState(initial);
  const [queue, setQueue] = useState<{ enabled: boolean; counts: Record<string, number> }>();
  const [error, setError] = useState("");
  const [changing, setChanging] = useState(false);
  useEffect(() => {
    let alive = true, fetching = false;
    async function refresh() {
      if (fetching) return;
      fetching = true;
      try {
        const [detail, status] = await Promise.all([fetch(`/__localmail/threads/${threadId}`, { method: "GET", cache: "no-store" }), fetch("/__localmail/extraction", { method: "GET", cache: "no-store" })]);
        if (!detail.ok || !status.ok) throw new Error();
        const [body, progress] = await Promise.all([detail.json(), status.json()]);
        if (alive) { setData(body.messages.find((m: { id: number }) => m.id === messageId)?.extraction); setQueue(progress); setError(""); }
      } catch { if (alive) setError("提取状态暂不可用"); }
      finally { fetching = false; }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [messageId, threadId]);
  async function control() {
    setChanging(true);
    try {
      const response = await fetch(`/__localmail/extraction/${queue?.enabled ? "pause" : "resume"}`, { method: "POST" });
      if (!response.ok) throw new Error();
      setQueue(await response.json()); setError("");
    } catch { setError("切换失败，请重试"); }
    finally { setChanging(false); }
  }
  const label = error || (data?.status === "ok" ? "AI 提取 · 待核对" : data?.status === "failed" ? "提取失败" : data?.status === "running" ? "正在提取" : "等待后台提取");
  return <section className="mw-fact-strip" aria-label="邮件关键资料">
    {rows.map((row, index) => <div className="mw-fact-row" key={index}>
      {index === 0 && <Popover trigger="click" title="后台阅读状态" content={<div className="mw-fact-evidence"><p>{data?.coverage || "本封新增正文与邮件头；附件尚未提取"}</p><p>{data?.model} · {data?.task_version} · 原文 #{messageId}</p><p>{data?.produced_at ? new Date(data.produced_at).toLocaleString() : "尚未完成"}</p><p>已提取 {queue?.counts?.ok || 0} · 待提取 {queue?.counts?.queued || 0} · 失败 {queue?.counts?.failed || 0}</p><p>{data?.reason || error || "单任务串行；清屏不删除记录；不会自动确认线索。"}</p><Button loading={changing} onClick={() => void control()}>{queue?.enabled ? "暂停后台提取（当前任务完成后）" : "继续提取 / 重试失败项"}</Button></div>}><Button type="text" className="mw-fact-state"><Tag color={data?.status === "failed" ? "error" : "blue"}>{label}</Tag></Button></Popover>}
      {row.map(([title, ...keys]) => {
        const facts = data?.status === "ok" ? data.facts.filter(f => keys.includes(f.key)) : [];
        return <Popover key={title} trigger="click" title={`${title} · 原文依据`} content={<div className="mw-fact-evidence">{facts.length ? facts.map((fact, i) => <div key={i}><strong>{fact.value}</strong><blockquote>{fact.quote}</blockquote></div>) : <p>{data?.status === "ok" ? "本封新增正文中未提取到明确依据；不代表历史邮件或附件中不存在。" : data?.reason || "尚未完成提取，未用猜测或空值代替结果。"}</p>}<small>{data?.model} · {data?.task_version} · 原文 #{messageId} · 待人工核对</small></div>}><button type="button" className={`mw-fact-cell ${facts.length ? "" : "is-empty"}`}><span>{title}</span><strong>{facts.length ? facts.map(f => f.value).join(" · ") : data?.status === "ok" ? "未提供" : data?.status === "failed" ? "提取失败" : "待提取"}</strong></button></Popover>;
      })}
    </div>)}
  </section>;
}
