import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router";
import { Alert, Button, Collapse, ConfigProvider, Descriptions, Drawer, Empty, Input, Select, Skeleton, Table, Tag, Tooltip } from "antd";
import zhCN from "antd/locale/zh_CN";
import { ArrowLeft, ChevronLeft, ChevronRight, Inbox, Languages, Layers, RefreshCw, Search, ShieldCheck, Sparkles, ExternalLink, FileText, Sun, Moon, PanelLeftClose, PanelLeftOpen, Info } from "lucide-react";
import { PaneResize } from "./pane-resize";
import { RealMailboxAsk } from "./real-mailbox-ask";
import { MailFacts, type MailExtraction } from "./mail-facts";
import { mailTheme } from "@/tokens/mail-theme";
import "@/tokens/real-mailbox.css";

type Reading = { status: string; model: string; produced_at: string; task_version: string; coverage?: string; payload: { summary_zh?: string; facts?: string[]; unverified?: string[] } };
type Thread = { id: number; subject: string; contact: string; email: string; date: string; count: number; preview: string; reading: Reading | null };
type Translation = { status: string; text_zh: string; model: string; task_version: string; produced_at: string; reason: string; coverage: string };
type Message = { id: number; subject: string; from_name: string; from_email: string; to_emails: string; sent_at: string; body_new: string; body_quoted: string; reading: Reading | null; extraction?: MailExtraction; translation?: Translation; attachments: { id: number; filename: string; size: number }[] };
type Job = { status: string; kind: string; result?: { status?: string; stored?: number; duplicate?: number; oversize?: number } };
type Mailbox = { address: string; threads: Thread[]; messages: number; coverage: string; job: Job };
type Filter = "all" | "pending" | "done" | "failed";
async function call<T>(path: string, method = "GET"): Promise<T> {
  const response = await fetch(`/__localmail${path}`, { method, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "本地邮件服务未连接，请检查 8910 服务");
  }
  return response.json();
}
const stamp = (date: string) => date ? new Date(date).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "时间未提供";
const readingLabel = (r: Reading | null) => r?.status === "ok" ? "已分析" : r?.status === "failed" ? "分析失败" : "未分析";
function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia("(max-width: 720px)").matches);
  useEffect(() => { const mq = window.matchMedia("(max-width: 720px)"); const change = () => setNarrow(mq.matches); mq.addEventListener("change", change); return () => mq.removeEventListener("change", change); }, []);
  return narrow;
}

export function RealMailbox() {
  const [box, setBox] = useState<Mailbox | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<{ id: number; messages: Message[] } | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState("newest");
  const [dark, setDark] = useState(() => localStorage.getItem("mail-theme") === "dark");
  const [job, setJob] = useState<Job>({ status: "idle", kind: "" });
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState<{ id: number; message: string } | null>(null);
  const [listOpen, setListOpen] = useState(true);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [listWidth, setListWidth] = useState(330);
  const [refreshId, setRefreshId] = useState(0);
  const [info, setInfo] = useState(false);
  const [overview, setOverview] = useState(true);
  const narrow = useNarrow();
  const submitting = useRef(false);
  const citation = useRef<number | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  useEffect(() => { localStorage.setItem("mail-theme", dark ? "dark" : "light"); }, [dark]);
  useEffect(() => {
    let alive = true;
    call<Mailbox>("/threads").then(data => { if (alive) { setBox(data); setJob(data.job); setError(""); setSelected(current => data.threads.some(t => t.id === current) ? current : data.threads[0]?.id ?? null); } }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [refreshId]);
  useEffect(() => {
    if (selected === null) return;
    let alive = true;
    call<{ messages: Message[] }>(`/threads/${selected}`).then(data => {
      if (alive) { setDetail({ id: selected, messages: data.messages }); setDetailError(null); setActive(citation.current ?? data.messages.at(-1)?.id ?? null); citation.current = null; }
    }).catch(e => { if (alive) setDetailError({ id: selected, message: e.message }); });
    return () => { alive = false; };
  }, [selected, refreshId]);
  useEffect(() => {
    if (job.status !== "running") return;
    let alive = true, fetching = false;
    const timer = window.setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try { const value = await call<Job>("/job"); if (alive) { setJob(value); if (value.status !== "running") setRefreshId(v => v + 1); } }
      catch (e) { if (alive) { setError(e instanceof Error ? e.message : String(e)); setJob({ status: "failed", kind: "" }); } }
      finally { fetching = false; }
    }, 2000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [job.status]);

  async function action(kind: "sync" | "analyze") {
    if (submitting.current || job.status === "running" || (kind === "analyze" && selected === null)) return;
    submitting.current = true;
    setError(""); setJob({ status: "running", kind });
    try { await call(kind === "sync" ? "/sync" : `/threads/${selected}/analyze`, "POST"); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setJob({ status: "failed", kind }); }
    finally { submitting.current = false; }
  }
  async function translate(messageId: number) {
    if (submitting.current || job.status === "running") return;
    submitting.current = true;
    setError(""); setJob({ status: "running", kind: "translate" });
    try { await call(`/messages/${messageId}/translate`, "POST"); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); setJob({ status: "failed", kind: "translate" }); }
    finally { submitting.current = false; }
  }
  const current = box?.threads.find(t => t.id === selected);
  const messages = detail?.id === selected ? detail.messages : [];
  const mail = messages.find(m => m.id === active) ?? messages.at(-1);
  const reading = messages.at(-1)?.reading;
  const visible = (box?.threads ?? []).filter(t => {
    const match = `${t.contact} ${t.email} ${t.subject} ${t.preview} ${t.reading?.payload.summary_zh || ""}`.toLowerCase().includes(query.toLowerCase());
    return match && (filter === "all" || filter === "pending" && !t.reading || filter === "done" && t.reading?.status === "ok" || filter === "failed" && t.reading?.status === "failed");
  }).sort((a, b) => sort === "oldest" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date));
  const position = visible.findIndex(t => t.id === selected);
  const busy = job.status === "running";
  const failed = job.status === "failed" || job.result?.status === "failed";
  const status = busy ? job.kind === "sync" ? "正在只读同步网易邮箱…" : job.kind === "translate" ? "正在翻译邮件正文…" : "正在通过本机 API 分析…" : failed ? "上次任务失败，请重试或检查服务" : job.status === "done" && job.kind === "sync" ? `同步完成 · 新增 ${job.result?.stored} / 已有 ${job.result?.duplicate} / 超限 ${job.result?.oversize}` : "本地已收取 · 网易企业邮箱";
  function choose(id: number) { citation.current = null; setSelected(id); setMobileDetail(true); }
  const themeConfig = mailTheme(dark);
  if (!box && error) return <ConfigProvider locale={zhCN} theme={themeConfig}><div className="mail-workbench" data-mode={dark ? "dark" : "light"}><header className="mw-top"><strong>mail2leads · 真实邮箱</strong></header><div className="mw-padded"><Alert type="error" showIcon title={error} description="未加载任何演示邮件。请检查本机邮件服务后重试。" action={<Button onClick={() => { setError(""); setRefreshId(v => v + 1); }}>重新连接</Button>} /></div></div></ConfigProvider>;
  return <ConfigProvider locale={zhCN} theme={themeConfig} componentSize="small" button={{ autoInsertSpace: false }}>
    <div className="mail-workbench" data-mode={dark ? "dark" : "light"}>
      <header className="mw-top"><div className="mw-brand"><Layers size={19} /><strong>mail2leads</strong><span>销售邮件工作台</span></div><div className="mw-top-actions"><Button type={askOpen ? "primary" : "default"} icon={<Sparkles size={14} />} onClick={() => setAskOpen(!askOpen)} aria-expanded={askOpen}>问邮箱</Button><Tag color="blue">真实邮箱 · 只读</Tag><Tooltip title="本地试点与服务信息"><Button type="text" aria-label="服务信息" icon={<Info size={16} />} onClick={() => setInfo(true)} /></Tooltip><Button type="text" aria-label="切换亮暗" icon={dark ? <Sun size={16} /> : <Moon size={16} />} onClick={() => setDark(!dark)} /></div></header>
      <div className={`mw-shell ${askOpen ? "mw-with-ask" : ""} ${!listOpen ? "mw-list-hidden" : ""} ${mobileDetail ? "mw-mobile-detail" : ""}`} style={{ "--mw-list-width": `${listWidth}px` } as CSSProperties}>
        <aside className="mw-nav"><div className="mw-account"><div className="mw-account-icon">G</div><strong>Glocal Storage</strong><span title={box?.address}>{box?.address || "连接中…"}</span></div><div className="mw-nav-label">邮箱</div><Button type={filter === "all" ? "primary" : "text"} block icon={<Inbox size={15} />} onClick={() => { setFilter("all"); setListOpen(true); setMobileDetail(false); }}>收件箱 <span className="mw-count">{box?.messages ?? "—"}</span></Button><Button type={filter === "pending" ? "primary" : "text"} block icon={<Sparkles size={15} />} onClick={() => { setFilter("pending"); setListOpen(true); setMobileDetail(false); }}>待分析 <span className="mw-count">{box?.threads.filter(t => !t.reading).length ?? "—"}</span></Button><div className="mw-nav-label">工具</div><Button type="text" block href="http://127.0.0.1:8800/" target="_blank" rel="noreferrer" icon={<ExternalLink size={15} />}>API 调用后台</Button><Button type="text" block icon={<Info size={15} />} onClick={() => setInfo(true)}>服务与同步范围</Button><div className="mw-nav-bottom"><ShieldCheck size={15} /><span>本机只读试点<br />不发送 · 不删除</span></div></aside>
        <section className="mw-list" aria-label="邮件列表"><div className="mw-list-head"><strong>收件箱 <span>{box?.messages ?? "—"}</span></strong><Tooltip title="隐藏邮件列表"><Button type="text" aria-label="隐藏邮件列表" icon={<PanelLeftClose size={15} />} onClick={() => { setListOpen(false); setMobileDetail(true); }} /></Tooltip></div><div className="mw-search"><Input allowClear prefix={<Search size={14} />} aria-label="搜索已收取邮件" placeholder="搜索发件人、标题、摘要" value={query} onChange={e => setQuery(e.target.value)} /></div><div className="mw-list-filters"><Select aria-label="分析状态" value={filter} onChange={setFilter} options={[{ value: "all", label: "全部状态" }, { value: "pending", label: "未分析" }, { value: "done", label: "已分析" }, { value: "failed", label: "分析失败" }]} /><Select aria-label="邮件排序" value={sort} onChange={setSort} options={[{ value: "newest", label: "最新优先" }, { value: "oldest", label: "最早优先" }]} /></div><div className="mw-list-meta"><span>{visible.length} 个话题</span><span>仅搜索已收取范围</span></div><div className="mw-list-scroll">{!box && !error && <div className="mw-padded"><Skeleton active paragraph={{ rows: 8 }} /></div>}{box && !visible.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的邮件" />}{visible.map(t => <Button type="text" key={t.id} className={`mw-mail-row ${selected === t.id ? "is-selected" : ""}`} aria-pressed={selected === t.id} onClick={() => choose(t.id)}><div className="mw-row-top"><strong>{t.contact}</strong><time>{stamp(t.date)}</time></div><div className="mw-row-subject">{t.subject}</div><div className="mw-row-preview">{t.reading?.payload.summary_zh || t.preview || "正文为空"}</div><div className="mw-row-bottom"><span data-status={t.reading?.status || "pending"}>{readingLabel(t.reading)}</span><span>{t.count} 封</span></div></Button>)}</div><div className="mw-list-footer"><ShieldCheck size={12} /> 原文保留 · AI 结果待核对</div><PaneResize label="调整邮件列表宽度" value={listWidth} min={270} max={460} onChange={setListWidth} onReset={() => setListWidth(330)} /></section>
        <main className="mw-reader"><div className="mw-toolbar"><div><Button type="text" aria-label="显示邮件列表" icon={narrow ? <ArrowLeft size={16} /> : <PanelLeftOpen size={16} />} onClick={() => { setListOpen(true); setMobileDetail(false); }} /><span>收件箱 / <strong>{current?.contact || "选择邮件"}</strong></span></div><div><span className="mw-position">{position >= 0 ? position + 1 : "—"} / {visible.length}</span><Button type="text" aria-label="上一话题" disabled={position <= 0} icon={<ChevronLeft size={16} />} onClick={() => choose(visible[position - 1].id)} /><Button type="text" aria-label="下一话题" disabled={position < 0 || position >= visible.length - 1} icon={<ChevronRight size={16} />} onClick={() => choose(visible[position + 1].id)} /><Button icon={<RefreshCw size={13} />} loading={busy && job.kind === "sync"} disabled={busy} onClick={() => void action("sync")}>同步邮箱</Button></div></div>
          {error && <Alert type="error" showIcon title={error} action={<Button onClick={() => { setDetail(null); setRefreshId(v => v + 1); }}>重新连接</Button>} />}
          {mail && selected !== null && <MailFacts key={mail.id} messageId={mail.id} threadId={selected} initial={mail.extraction} />}
          <div className="mw-reader-scroll">{current ? <><div className="mw-subject"><Tag color={current.reading?.status === "ok" ? "blue" : "default"}>{readingLabel(current.reading)}</Tag><h1>{current.subject}</h1><div><strong>{current.contact}</strong><span>{current.email}</span><span>{current.count} 封往来</span></div></div>{detailError?.id === selected ? <Alert type="error" showIcon title={detailError.message} action={<Button onClick={() => setRefreshId(v => v + 1)}>重试</Button>} /> : !mail ? <Skeleton active paragraph={{ rows: 8 }} /> : <div className="mw-reading-grid"><section className="mw-overview"><div className="mw-overview-head"><Button type="text" onClick={() => setOverview(!overview)} aria-expanded={overview} icon={<Layers size={14} />}>专题总览 <span className="mw-muted">{overview ? "收起" : "展开"}</span></Button><Button type="primary" ghost icon={<Sparkles size={13} />} disabled={busy} loading={busy && job.kind === "analyze"} onClick={() => void action("analyze")}>{reading ? "重新分析" : "分析最新来信"}</Button></div>{overview && <><div className="mw-summary"><div className="mw-section-label">最新来信摘要 <span>不是全话题结论</span></div>{reading?.status === "ok" ? <>{!!reading.payload.unverified?.length && <Alert type="warning" showIcon title={`数字待核对：${reading.payload.unverified.join("、")}`} />}<p>{reading.payload.summary_zh}</p>{!!reading.payload.facts?.length && <Collapse ghost size="small" items={[{ key: "facts", label: `需求明细 · ${reading.payload.facts.length} 项`, children: <ul>{reading.payload.facts.map((f, i) => <li key={i}>{f}</li>)}</ul> }]} />}<div className="mw-provenance">{reading.model} · {reading.task_version}<br />{stamp(reading.produced_at)} · 来源：最新来信 #{messages.at(-1)?.id} · {reading.coverage || "待人工核对"}</div></> : <Alert type={reading?.status === "failed" ? "error" : "info"} showIcon title={reading?.status === "failed" ? "本封分析失败，没有可用读数" : "原文已就绪，尚未分析"} description="摘要仍可按需生成；顶部结构化资料由后台自动提取，点击状态标签可查看进度或暂停。" />}</div><div className="mw-correspondence"><div className="mw-section-label">邮件往来 <span>{messages.length} 封 · 时间正序</span></div><Table size="small" pagination={false} rowKey="id" dataSource={messages} rowClassName={m => m.id === mail.id ? "mw-active-original" : ""} columns={[{ title: "时间", dataIndex: "sent_at", render: stamp }, { title: "标题 / 发件人", render: (_, m: Message) => <Button type="link" className="mw-timeline-link" onClick={() => setActive(m.id)}><strong>{m.subject}</strong><small>{m.from_name || m.from_email}</small></Button> }]} /></div></>}</section>
          <article className="mw-original"><div className="mw-original-head"><strong><FileText size={14} />邮件原文</strong><div><Button size="small" icon={<Languages size={13} />} disabled={!mail.body_new.trim() || busy} loading={busy && job.kind === "translate"} onClick={() => void translate(mail.id)}>{mail.translation?.status === "ok" ? "重新翻译" : "翻译正文"}</Button><span>{stamp(mail.sent_at)}</span></div></div><h2>{mail.subject}</h2><Descriptions size="small" column={1} items={[{ key: "from", label: "发件人", children: `${mail.from_name} <${mail.from_email}>` }, { key: "to", label: "收件人", children: mail.to_emails || box?.address }]} /><div className="mw-body">{mail.body_new || "（正文为空）"}</div>{mail.translation && <section className="mw-translation"><div className="mw-section-label">中文翻译 <span>{mail.translation.status === "ok" ? "当前正文 · 待核对" : "翻译失败"}</span></div>{mail.translation.status === "ok" ? <><div className="mw-body">{mail.translation.text_zh}</div><div className="mw-provenance">{mail.translation.model} · {mail.translation.task_version}<br />{stamp(mail.translation.produced_at)} · {mail.translation.coverage}</div></> : <Alert type="error" showIcon title={mail.translation.reason || "翻译未完成"} />}</section>}{mail.body_quoted && <Collapse ghost size="small" items={[{ key: "quoted", label: "展开引用历史", children: <div className="mw-body">{mail.body_quoted}</div> }]} />}{!!mail.attachments.length && <div className="mw-files"><div className="mw-section-label">附件 <span>清单预览，暂未开放下载</span></div>{mail.attachments.map(f => <div key={f.id}><FileText size={15} /><span>{f.filename}</span><small>{(f.size / 1024).toFixed(1)} KB</small></div>)}</div>}</article></div>}</> : box ? <Empty description="请选择一封邮件" /> : !error ? <Skeleton active paragraph={{ rows: 10 }} /> : null}</div>
          <footer className="mw-status" role="status"><span className={failed ? "mw-failed" : ""}><span className={busy ? "mw-status-dot busy" : "mw-status-dot"} />{status}</span><Button type="link" onClick={() => setInfo(true)}>同步范围</Button></footer>
        </main>
        <RealMailboxAsk open={askOpen} onClose={() => setAskOpen(false)} onBusy={value => { if (value) setJob({ status: "running", kind: "ask" }); else setRefreshId(v => v + 1); }} onCitation={(thread, message) => { if (selected === thread) setActive(message); else { citation.current = message; setSelected(thread); } setMobileDetail(true); if (narrow) setAskOpen(false); }} />
      </div>
      <Drawer title="服务与同步范围" open={info} onClose={() => setInfo(false)} size={narrow ? "100%" : "default"}><Descriptions column={1} bordered items={[{ key: "mail", label: "邮箱", children: box?.address || "未连接" }, { key: "count", label: "本地原文", children: `${box?.messages ?? 0} 封 / ${box?.threads.length ?? 0} 个话题` }, { key: "scope", label: "同步范围", children: box?.coverage || "INBOX · 最近 30 天 · 每次最多 30 封 · 单封 2 MB" }, { key: "mode", label: "工作模式", children: "手动同步、入库后自动提取结构化资料；不发送、不删除、不改网易已读状态" }]} /><div className="mw-drawer-note"><Alert type="warning" showIcon title="本机只读试点" description="已支持本地已同步邮件问答；尚未接入员工登录、网易全量检索和完整话题总结，不用于公网部署。" /><p>AI 经独立 API 网关接入。模型、输入输出、token 与耗时在 openapi 后台查看。</p><Button href="http://127.0.0.1:8800/" target="_blank" rel="noreferrer" icon={<ExternalLink size={14} />}>打开 API 后台</Button><p><Link to="/design">查看旧设计样本（虚构数据）</Link></p></div></Drawer>
    </div>
  </ConfigProvider>;
}
