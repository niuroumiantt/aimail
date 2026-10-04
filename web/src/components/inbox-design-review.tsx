import { useEffect, useReducer, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { ArrowDownLeft, ArrowLeft, ArrowUpRight, BriefcaseBusiness, Check, ChevronDown, ChevronRight, CircleUserRound, FileText, Inbox, Layers, Mail, MapPin, Newspaper, PanelLeftClose, PanelLeftOpen, PenLine, RefreshCw, Search, Sparkles, Users, X, Zap, type LucideIcon } from "lucide-react";
import "@/tokens/inbox-design-review.css";

type Filter = "all" | "lead" | "other";
type Category = "买方询价" | "卖方供货" | "报价往来" | "财务账单" | "新闻订阅" | "系统通知";
type DemoMail = {
  id: string; from: string; fromEmail: string; customerEmail: string; initials: string;
  subject: string; category: Category; lead: boolean; time: string; date: string;
  summary: string; body: string[]; quote?: string; outgoing?: boolean;
};
type DemoProject = {
  id: string; title: string; kind: string; quantity: string; spec: string; terms: string;
  description: string; change: string; sourceId: string; timeline: { mailId: string; label: string }[];
};
type CustomerSnapshot = { sourceRevision: string; version: number; updatedAt: string; projects: DemoProject[] };
export type DemoInboxState = { messages: DemoMail[]; snapshots: Record<string, CustomerSnapshot>; notice: string };
export type DemoInboxAction = { type: "refresh" } | { type: "demo-new-mail" };
const primaryCustomer = "purchasing@obsidian.example";

// All names, messages and cumulative summaries are authored fixtures, not model results.
const seedMessages: DemoMail[] = [
  { id: "gpu-revised", from: "曜石计算", fromEmail: primaryCustomer, customerEmail: primaryCustomer, initials: "曜", subject: "Re: H200 采购 · 数量调整为 2 台", category: "买方询价", lead: true, time: "09:42", date: "今天 09:42", summary: "同一 GPU 项目由 4 台调整为 2 台，其余配置和交付要求不变。", body: ["你好，谢谢你们的报价。我们调整了机房扩容计划，请将本次 H200 GPU 服务器采购数量从 4 台改为 2 台。", "每台 8 张 GPU 的配置保持不变，交付仍为 CIF Singapore，希望在 3 周内完成。请按 2 台重新出一份正式报价。", "之前另行询问的 12 台存储节点是独立项目，不受这次数量调整影响。谢谢。"], quote: "此前我方报价：按最初 4 台 H200 GPU 服务器需求准备配置与报价，质保 12 个月；请确认数量和交期。" },
  { id: "storage-inquiry", from: "曜石计算", fromEmail: primaryCustomer, customerEmail: primaryCustomer, initials: "曜", subject: "独立项目：2U 存储节点 · 12 台", category: "买方询价", lead: true, time: "09:10", date: "今天 09:10", summary: "同一客户另有 12 台存储节点需求，与 GPU 采购分别处理。", body: ["这是另一项采购，与 H200 GPU 项目独立。我们需要 12 台 2U、24 盘位的 NVMe 存储节点，配置双电源。", "请推荐合适配置，并单独提供这个项目的报价和预计交付时间。" ] },
  { id: "supplier-memory", from: "北辰硬件", fromEmail: "stock@polaris.example", customerEmail: "stock@polaris.example", initials: "北", subject: "DDR5 64GB RDIMM · 200 条现货供应", category: "卖方供货", lead: true, time: "08:56", date: "今天 08:56", summary: "供应商提供 200 条原厂 DDR5 现货，可索取料号和单价。", body: ["我们有 200 条原厂全新 DDR5 64GB ECC RDIMM 现货，可提供批次照片与测试报告。", "如有采购需求，请告知数量和目的地，我们提供详细报价。" ] },
  { id: "ssd-quote", from: "松岚科技", fromEmail: "sales@pinecloud.example", customerEmail: "sales@pinecloud.example", initials: "松", subject: "Re: 企业级 SSD · 更新报价与质保", category: "报价往来", lead: true, time: "08:40", date: "今天 08:40", summary: "供货报价：3.84TB SSD 500 片，单价 USD 95，质保 12 个月。", body: ["关于你方的 SSD 采购需求，我们可以提供 500 片 3.84TB 企业级 SATA SSD。", "单价 USD 95，质保 12 个月，款到后 5 个工作日发货。请确认是否需要检测报告。" ] },
  { id: "bill", from: "晴川财务", fromEmail: "billing@clearwater.example", customerEmail: "billing@clearwater.example", initials: "晴", subject: "9 月办公服务账单已出", category: "财务账单", lead: false, time: "08:30", date: "今天 08:30", summary: "办公服务账单通知，需要财务核对和归档。", body: ["你好，你的 9 月办公服务账单已经生成。请在账户内查看明细并核对。", "本邮件是日常账单通知，无需回复。" ] },
  { id: "gpu-quote", from: "青岚贸易（我方）", fromEmail: "sales@qinglan.example", customerEmail: primaryCustomer, initials: "青", subject: "Re: H200 采购 · 我方报价", category: "报价往来", lead: true, time: "昨天", date: "昨天 15:20", summary: "我方按最初 4 台需求提供报价；客户后续已调整数量。", outgoing: true, body: ["你好，感谢询价。我们按 4 台 H200 GPU 服务器、每台 8 张 GPU 的需求准备了配置与报价。", "报价条件为 CIF Singapore，质保 12 个月。请确认数量和交期，我们再出正式报价。"], quote: "客户最初询价：计划采购 4 台 H200 GPU 服务器，每台 8 张 GPU，CIF Singapore，期望 3 周内交付。" },
  { id: "news", from: "每日科技简报", fromEmail: "digest@techdaily.example", customerEmail: "digest@techdaily.example", initials: "简", subject: "本周数据中心与 AI 行业新闻", category: "新闻订阅", lead: false, time: "昨天", date: "昨天 08:00", summary: "行业订阅简报，没有具体采购或供货请求。", body: ["本周简报：数据中心建设、AI 算力与新一代存储技术。", "这是你订阅的行业新闻，不包含具体询价、采购或供货请求。" ] },
  { id: "security", from: "云端安全", fromEmail: "notice@cloudsafe.example", customerEmail: "notice@cloudsafe.example", initials: "云", subject: "你的账号已启用双重验证", category: "系统通知", lead: false, time: "周五", date: "周五 11:30", summary: "账号安全通知，确认双重验证已启用。", body: ["你的账号已成功启用双重验证。", "如果这不是你本人操作，请前往账号安全页面检查。" ] },
  { id: "gpu-initial", from: "曜石计算", fromEmail: primaryCustomer, customerEmail: primaryCustomer, initials: "曜", subject: "H200 GPU 服务器 · 最初 4 台询价", category: "买方询价", lead: true, time: "周四", date: "周四 10:15", summary: "首次询问 4 台 H200 服务器；这是历史邮件，累计变化见右侧。", body: ["你好，我们计划为新加坡机房采购 4 台 H200 GPU 服务器，每台配置 8 张 GPU。", "请提供完整配置、CIF Singapore 报价、质保条款，以及能否在 3 周内交付。收到报价后我们会评估采购。" ] },
];
const newDemoMail: DemoMail = {
  id: "gpu-new", from: "曜石计算", fromEmail: primaryCustomer, customerEmail: primaryCustomer, initials: "曜",
  subject: "Re: H200 采购 · 最终调整为 3 台", category: "买方询价", lead: true, time: "刚刚", date: "今天 10:05（演示）",
  summary: "演示新增来信：同一 GPU 项目由 2 台调整为 3 台，其余要求不变。",
  body: ["你好，我们已完成内部确认，请把 H200 GPU 服务器数量从 2 台调整为 3 台。", "每台 8 张 GPU、CIF Singapore 与 3 周内交付的要求保持不变。请按 3 台更新报价。", "12 台存储节点仍是独立采购项目，数量不变。"],
  quote: "此前客户调整：请将本次 H200 GPU 服务器采购数量从 4 台改为 2 台，其余配置和交付要求不变。",
};

function revision(messages: DemoMail[], email: string) {
  return messages.filter(mail => mail.customerEmail === email).map(mail => mail.id).sort().join("|");
}

export function createDemoInboxState(): DemoInboxState {
  const messages = [...seedMessages];
  const snapshots: Record<string, CustomerSnapshot> = {
    [primaryCustomer]: { sourceRevision: revision(messages, primaryCustomer), version: 1, updatedAt: "今天 09:42", projects: [
      { id: "gpu", title: "H200 GPU 服务器采购", kind: "买方询价", quantity: "2 台", spec: "每台 8 张 GPU", terms: "CIF Singapore · 3 周内", description: "客户最新要求采购 2 台 H200 GPU 服务器，已收到我方按最初 4 台需求准备的报价，需要更新正式报价。", change: "数量 4 → 2 台；配置和交付要求不变", sourceId: "gpu-revised", timeline: [{ mailId: "gpu-initial", label: "客户最初询价 · 4 台" }, { mailId: "gpu-quote", label: "我方按 4 台提供报价" }, { mailId: "gpu-revised", label: "客户调整数量 · 2 台" }] },
      { id: "storage", title: "2U 存储节点采购", kind: "独立买方项目", quantity: "12 台", spec: "24 盘位 NVMe · 双电源", terms: "配置、报价和交期待确认", description: "单独采购 12 台 2U 存储节点，与 GPU 项目分开报价，数量不受 GPU 调整影响。", change: "新增独立项目 · 数量保持 12 台", sourceId: "storage-inquiry", timeline: [{ mailId: "storage-inquiry", label: "独立存储需求 · 12 台" }] },
    ] },
    "stock@polaris.example": { sourceRevision: revision(messages, "stock@polaris.example"), version: 1, updatedAt: "今天 08:56", projects: [{ id: "memory", title: "DDR5 内存供货", kind: "卖方供货", quantity: "200 条", spec: "64GB ECC RDIMM · 原厂全新", terms: "完整料号、价格和交期待确认", description: "供应商有 200 条 DDR5 内存现货，希望寻找采购方，可提供批次照片和测试报告。", change: "新供货信息 · 单价尚未提供", sourceId: "supplier-memory", timeline: [{ mailId: "supplier-memory", label: "库存供货 · 200 条" }] }] },
    "sales@pinecloud.example": { sourceRevision: revision(messages, "sales@pinecloud.example"), version: 1, updatedAt: "今天 08:40", projects: [{ id: "ssd", title: "企业级 SSD 报价", kind: "报价往来", quantity: "500 片", spec: "3.84TB · SATA", terms: "USD 95 / 片 · 质保 12 个月", description: "供应商可提供 500 片企业级 SSD，款到后 5 个工作日发货，检测报告待确认。", change: "已收到供货报价和质保条款", sourceId: "ssd-quote", timeline: [{ mailId: "ssd-quote", label: "最新供货报价" }] }] },
  };
  return { messages, snapshots, notice: "固定示例摘要已就绪 · 未连接真实邮箱或模型" };
}

/** Demo-only source revision behavior; does not claim production/model caching. */
export function demoInboxReducer(state: DemoInboxState, action: DemoInboxAction): DemoInboxState {
  if (action.type === "refresh") return { ...state, notice: "没有新邮件 · 示例摘要已是最新，保留现有内容" };
  if (state.messages.some(mail => mail.id === newDemoMail.id)) return { ...state, notice: "演示来信已经加入 · 没有更多新邮件" };
  const messages = [newDemoMail, ...state.messages];
  const previous = state.snapshots[primaryCustomer];
  const gpu = previous.projects[0];
  const updated: CustomerSnapshot = {
    sourceRevision: revision(messages, primaryCustomer), version: previous.version + 1, updatedAt: newDemoMail.date,
    projects: [{ ...gpu, quantity: "3 台", description: "客户最新确认采购 3 台 H200 GPU 服务器，配置和交付要求不变，需要按 3 台更新报价。", change: "数量 2 → 3 台；独立存储项目仍为 12 台", sourceId: newDemoMail.id, timeline: [...gpu.timeline, { mailId: newDemoMail.id, label: "客户最新确认 · 3 台" }] }, previous.projects[1]],
  };
  return { messages, snapshots: { ...state.snapshots, [primaryCustomer]: updated }, notice: "已加入 1 封虚构来信 · 固定示例摘要更新为 3 台（非模型调用）" };
}

const customerProfiles: Record<string, { name: string; person: string; location: string; role: string }> = {
  [primaryCustomer]: { name: "曜石计算", person: "程安 · 采购负责人", location: "新加坡", role: "客户采购" },
  "stock@polaris.example": { name: "北辰硬件", person: "周棠 · 库存销售", location: "中国 · 深圳", role: "供应商供货" },
  "sales@pinecloud.example": { name: "松岚科技", person: "许舟 · 业务联系人", location: "中国 · 杭州", role: "供应商报价" },
};
function Icon({ icon: Glyph }: { icon: LucideIcon }) { return <Glyph strokeWidth={1.75} aria-hidden="true" />; }
function CategoryBadge({ lead, category, full = false }: { lead: boolean; category?: string; full?: boolean }) {
  return lead ? <span className="ir-lead-badge"><Icon icon={Zap} />SALES LEAD{full && " · 买卖线索"}</span> : <span className="ir-category-badge">{category}</span>;
}
function MailRow({ mail, selected, onSelect }: { mail: DemoMail; selected: boolean; onSelect: () => void }) {
  return <button type="button" className="ir-mail-row" data-lead={mail.lead} aria-label={`${mail.subject}，${mail.from}，${mail.category}${mail.lead ? "，SALES LEAD 买卖线索" : ""}`} aria-pressed={selected} onClick={onSelect}>
    <span className="ir-row-heading"><span>{mail.from}</span><time>{mail.time}</time></span>
    <span className="ir-row-subject">{mail.subject}</span>
    <span className="ir-row-summary">{mail.summary}</span>
    <span className="ir-row-meta"><CategoryBadge lead={mail.lead} category={mail.category} />{mail.lead && <span className="ir-row-category">{mail.outgoing ? <Icon icon={ArrowUpRight} /> : <Icon icon={ArrowDownLeft} />}{mail.outgoing ? "我方已发出" : mail.category}</span>}</span>
  </button>;
}

export function InboxDesignReview() {
  const [state, dispatch] = useReducer(demoInboxReducer, undefined, createDemoInboxState);
  const [density, setDensity] = useState<"compact" | "summary">("summary");
  const [filter, setFilter] = useState<Filter>("all");
  const [grouped, setGrouped] = useState(true);
  const [expanded, setExpanded] = useState<string[]>([primaryCustomer]);
  const [selectedId, setSelectedId] = useState("gpu-revised");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [navWidth, setNavWidth] = useState(184);
  const [mobileView, setMobileView] = useState<"list" | "mail" | "customer">("list");
  const [replyOpen, setReplyOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [draftNotice, setDraftNotice] = useState("");
  const drag = useRef<{ x: number; width: number } | null>(null);
  const readerScroll = useRef<HTMLDivElement>(null);
  const draftEditor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (readerScroll.current) readerScroll.current.scrollTop = 0; }, [selectedId]);
  useEffect(() => { if (replyOpen) draftEditor.current?.focus(); }, [replyOpen]);
  const selected = state.messages.find(mail => mail.id === selectedId)!;
  const snapshot = state.snapshots[selected.customerEmail];
  const profile = customerProfiles[selected.customerEmail];
  const customerMails = state.messages.filter(mail => mail.customerEmail === selected.customerEmail);
  const leadCount = state.messages.filter(mail => mail.lead).length;
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matches = (mail: DemoMail, nextFilter = filter) => (nextFilter === "all" || (nextFilter === "lead" ? mail.lead : !mail.lead)) && `${mail.from} ${mail.fromEmail} ${mail.customerEmail} ${customerProfiles[mail.customerEmail]?.name ?? ""} ${mail.subject} ${mail.summary} ${mail.category}`.toLocaleLowerCase().includes(normalizedQuery);
  const visible = state.messages.filter(mail => matches(mail));
  const groups = new Map<string, DemoMail[]>();
  for (const mail of visible) groups.set(mail.customerEmail, [...(groups.get(mail.customerEmail) ?? []), mail]);
  const clamp = (value: number) => Math.min(260, Math.max(160, value));
  const filters: { id: Filter; title: string; count: number; icon: LucideIcon }[] = [
    { id: "all", title: "全部邮件", count: state.messages.length, icon: Inbox },
    { id: "lead", title: "买卖线索", count: leadCount, icon: BriefcaseBusiness },
    { id: "other", title: "日常邮件", count: state.messages.length - leadCount, icon: Mail },
  ];
  function selectMail(mail: DemoMail) { setSelectedId(mail.id); setMobileView("mail"); setReplyOpen(false); setDraftNotice(""); }
  function changeFilter(next: Filter) {
    setFilter(next); const matching = state.messages.filter(mail => matches(mail, next));
    if (matching.length && !matching.some(mail => mail.id === selectedId)) selectMail(matching[0]);
    setMobileView("list");
  }
  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { x: event.clientX, width: navWidth };
  }
  function jumpSource(id: string) { const mail = state.messages.find(item => item.id === id); if (mail) selectMail(mail); }

  return <div className="ir" data-density={density}>
    <header className="ir-review-header"><div><span className="ir-eyebrow">AIMAIL / CUSTOMER WORKSPACE</span><h1>邮件在左，客户需求始终在右。</h1><p>融合工作区预览 · 全部为虚构客户、邮件与固定示例摘要</p></div><div className="ir-demo-tools"><button type="button" onClick={() => dispatch({ type: "refresh" })}><Icon icon={RefreshCw} />刷新演示</button><button type="button" className="ir-demo-add" disabled={state.messages.some(mail => mail.id === "gpu-new")} onClick={() => dispatch({ type: "demo-new-mail" })}><Icon icon={Mail} />{state.messages.some(mail => mail.id === "gpu-new") ? "示例来信已加入" : "演示新增来信"}</button></div></header>
    <div className="ir-preview-bar"><span role="status">{state.notice}</span><span>预览交互 · 无真实收信、模型调用或发送</span></div>
    <div className="ir-workspace" data-collapsed={collapsed} data-mobile-view={mobileView} style={{ "--ir-nav-size": navWidth } as CSSProperties}>
      <aside className="ir-sidebar" aria-label="邮箱导航"><div className="ir-brand"><span className="ir-brandmark"><Icon icon={Layers} /></span>{!collapsed && <b>aimail</b>}<button type="button" className="ir-icon-button" aria-label={collapsed ? "展开左侧面板" : "隐藏左侧面板"} onClick={() => setCollapsed(!collapsed)}><Icon icon={collapsed ? PanelLeftOpen : PanelLeftClose} /></button></div>{!collapsed && <div className="ir-account"><span className="ir-avatar">青</span><div><b>青岚贸易</b><small>示例销售邮箱</small></div></div>}
        <nav>{filters.map(item => <button type="button" key={item.id} aria-label={`${item.title}，${item.count} 封`} aria-pressed={filter === item.id} className="ir-nav-item" onClick={() => changeFilter(item.id)}><Icon icon={item.icon} />{!collapsed && <><span>{item.title}</span><span className="ir-count">{item.count}</span></>}</button>)}</nav>{!collapsed && <div className="ir-sidebar-footer"><Icon icon={CircleUserRound} /><span>人确认 · 人回复<small>仅设计演示</small></span></div>}
        {!collapsed && <div className="ir-resize" role="separator" aria-label="调整左侧面板宽度" aria-orientation="vertical" aria-valuemin={160} aria-valuemax={260} aria-valuenow={navWidth} tabIndex={0} title="拖动调宽；方向键微调；Home 恢复" onPointerDown={startResize} onPointerMove={event => { if (drag.current) setNavWidth(clamp(drag.current.width + event.clientX - drag.current.x)); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} onDoubleClick={() => setNavWidth(184)} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setNavWidth(width => clamp(width + (event.key === "ArrowRight" ? 12 : -12))); } if (event.key === "Home") { event.preventDefault(); setNavWidth(184); } }} />}
      </aside>

      <section className="ir-mailbox" aria-label="邮件列表"><div className="ir-mailbox-heading"><span className="ir-eyebrow">INBOX</span><h2>{filters.find(item => item.id === filter)!.title}<span>{visible.length}</span></h2></div><nav className="ir-mobile-filters" aria-label="移动端邮件分类">{filters.map(item => <button key={item.id} type="button" aria-pressed={filter === item.id} onClick={() => changeFilter(item.id)}>{item.title}<span>{item.count}</span></button>)}</nav>
        <label className="ir-search"><Icon icon={Search} /><input aria-label="搜索示例邮件" placeholder="搜索联系人、型号或主题" value={query} onChange={event => setQuery(event.target.value)} /></label><div className="ir-list-controls"><div className="ir-density"><button type="button" aria-pressed={density === "compact"} onClick={() => setDensity("compact")}>简洁</button><button type="button" aria-pressed={density === "summary"} onClick={() => setDensity("summary")}>概括</button></div><label className="ir-group-toggle"><input type="checkbox" checked={grouped} onChange={event => setGrouped(event.target.checked)} /><Icon icon={Users} />按联系人聚拢</label></div>
        <div className="ir-mail-list">{visible.length === 0 ? <div className="ir-empty"><Icon icon={Search} /><b>没有匹配的示例邮件</b><p>试试其他主题、型号或发件人。</p></div> : grouped ? [...groups.entries()].map(([email, mails]) => <div className="ir-sender-group" key={email}><button type="button" className="ir-group-heading" aria-label={`${customerProfiles[email]?.name ?? mails[0].from}，${email}，${mails.length} 封往来，${mails.filter(mail => mail.lead).length} 条买卖线索`} aria-expanded={expanded.includes(email)} onClick={() => setExpanded(current => current.includes(email) ? current.filter(item => item !== email) : [...current, email])}><Icon icon={expanded.includes(email) ? ChevronDown : ChevronRight} /><span><b>{customerProfiles[email]?.name ?? mails[0].from}</b><small>{email}</small></span><span className="ir-group-count">{mails.length}</span>{mails.some(mail => mail.lead) && <span className="ir-group-lead" title="包含买卖线索">LEAD</span>}</button>{expanded.includes(email) && mails.map(mail => <MailRow key={mail.id} mail={mail} selected={selectedId === mail.id} onSelect={() => selectMail(mail)} />)}</div>) : visible.map(mail => <MailRow key={mail.id} mail={mail} selected={selectedId === mail.id} onSelect={() => selectMail(mail)} />)}</div><div className="ir-list-footer"><span>{grouped ? `${groups.size} 位联系人 · ${visible.length} 封往来` : `${visible.length} 封示例邮件`}</span><span>{density === "compact" ? "标题为主" : "3–4 行概括"}</span></div>
      </section>

      <main className="ir-reader" aria-label="邮件阅读区"><div className="ir-reader-toolbar"><button type="button" className="ir-mobile-back" onClick={() => setMobileView("list")}><Icon icon={ArrowLeft} />邮件列表</button><span>邮件原文<Icon icon={ChevronRight} />{selected.category}</span><div><button type="button" className="ir-customer-trigger" aria-expanded={mobileView === "customer"} onClick={() => setMobileView("customer")}><Icon icon={CircleUserRound} />客户需求</button><button type="button" className="ir-reply-trigger" aria-expanded={replyOpen} onClick={() => { setReplyOpen(!replyOpen); setDraftNotice(""); }}><Icon icon={PenLine} />{replyOpen ? "收起草稿" : "回复草稿"}</button></div></div>
        <div className="ir-reader-scroll" ref={readerScroll}><article className="ir-reader-content"><div className="ir-message-category"><CategoryBadge lead={selected.lead} category={selected.category} full />{selected.outgoing && <span className="ir-outgoing">我方历史发出邮件</span>}</div><h2 className="ir-subject">{selected.subject}</h2><div className="ir-sender"><span className="ir-avatar">{selected.initials}</span><div><b>{selected.from}</b><span>{selected.fromEmail}</span>{selected.outgoing && <small>收件人：{selected.customerEmail}</small>}</div><time>{selected.date}</time></div>
          <section className="ir-original" aria-label="邮件原文">{selected.body.map(paragraph => <p key={paragraph}>{paragraph}</p>)}<p className="ir-signature">{selected.from}<br />{selected.fromEmail}</p></section>{selected.quote && <details className="ir-quoted-history"><summary><Icon icon={ChevronRight} />展开邮件内的历史引用</summary><blockquote>{selected.quote}</blockquote><small>引用属于历史原文，不代表最新累计需求。</small></details>}
          {replyOpen && <section className="ir-local-reply" aria-label="本地回复草稿"><header><span><Icon icon={PenLine} />回复 {selected.customerEmail}</span><button type="button" aria-label="关闭回复草稿" onClick={() => setReplyOpen(false)}><Icon icon={X} /></button></header><textarea ref={draftEditor} aria-label="编辑本地回复草稿" placeholder="在这里写回复；仅保留在当前预览中。" value={drafts[selected.id] ?? ""} onChange={event => { setDrafts(current => ({ ...current, [selected.id]: event.target.value })); setDraftNotice(""); }} /><footer><span>本地演示 · 不会发出邮件</span><button type="button" onClick={() => { setDraftNotice("草稿已保留在当前预览中，未发送"); setReplyOpen(false); }}>保留草稿</button></footer></section>}{draftNotice && <p className="ir-draft-status" role="status"><Icon icon={Check} />{draftNotice}</p>}
          <div className="ir-reading-note"><Icon icon={FileText} />当前查看的是这一封原文。右侧始终显示该客户全部往来的最新累计需求。</div></article></div><footer className="ir-reader-footer"><span>虚构邮件 · 仅设计预览</span><span>原文与客户需求独立滚动</span></footer>
      </main>

      <aside className="ir-customer-panel" aria-label="客户需求栏"><header className="ir-customer-panel-heading"><span><Icon icon={CircleUserRound} />客户工作区</span><button type="button" className="ir-customer-close" aria-label="返回邮件原文" onClick={() => setMobileView("mail")}><Icon icon={X} /></button></header><div className="ir-customer-scroll"><section className="ir-customer-card" aria-label="客户信息"><div className="ir-customer-name"><span className="ir-avatar">{profile?.name.slice(0, 1) ?? selected.initials}</span><div><h2>{profile?.name ?? selected.from}</h2><span>{profile?.person ?? "日常邮件发件方"}</span></div></div><p className="ir-customer-email">{selected.customerEmail}</p><div className="ir-customer-location"><span><Icon icon={MapPin} />{profile?.location ?? "地区未提供"}</span><span>{profile?.role ?? selected.category}</span></div><div className="ir-customer-scope"><Icon icon={Mail} />{customerMails.length} 封往来 · 当前示例邮箱内该联系人全部往来<small>包含来信和我方历史报价；不受列表分组影响</small></div></section>
          {snapshot ? <><section className="ir-cumulative-summary" aria-label="累计需求摘要"><div className="ir-section-heading"><span><Icon icon={Sparkles} />累计需求摘要</span><small>示例 v{snapshot.version}</small></div><p className="ir-summary-subtitle">截至 {snapshot.updatedAt} · 当前需求</p>{snapshot.projects.map(project => <article className="ir-project" aria-label={project.title} key={project.id}><div className="ir-project-heading"><span>{project.kind}</span><b>{project.quantity}</b></div><h3>{project.title}</h3><p>{project.description}</p><dl><div><dt>产品规格</dt><dd>{project.spec}</dd></div><div><dt>交付 / 条件</dt><dd>{project.terms}</dd></div></dl><div className="ir-latest-change"><span>最新变化</span><strong>{project.change}</strong></div><button type="button" className="ir-source-button" onClick={() => jumpSource(project.sourceId)}><Icon icon={FileText} /><span>查看原文来源<small>{state.messages.find(mail => mail.id === project.sourceId)!.date}</small></span><Icon icon={ArrowUpRight} /></button></article>)}<div className="ir-summary-disclosure"><Icon icon={CircleUserRound} />固定示例摘要 · 非真实模型结果<br />业务字段需人工核对与确认。</div></section>
          <section className="ir-customer-timeline" aria-label="客户往来时间线"><h3>往来与来源</h3>{snapshot.projects.map(project => <div className="ir-timeline-project" key={project.id}><h4>{project.title}</h4>{project.timeline.map(entry => <button type="button" key={entry.mailId} aria-label={`查看来源邮件：${entry.label}`} aria-pressed={selectedId === entry.mailId} onClick={() => jumpSource(entry.mailId)}><span className="ir-timeline-dot" /><span>{entry.label}<small>{state.messages.find(mail => mail.id === entry.mailId)!.date}</small></span><Icon icon={ChevronRight} /></button>)}</div>)}</section></> : <section className="ir-nonbusiness" aria-label="日常邮件信息"><Icon icon={selected.category === "新闻订阅" ? Newspaper : FileText} /><h3>{selected.category}</h3><p>这组邮件没有买卖需求，不建立交易项目。</p><small>此分类为固定演示数据。</small></section>}
        </div><footer className="ir-customer-footer"><Icon icon={Check} />阅读旧信不会回退累计需求</footer></aside>
    </div>
  </div>;
}
