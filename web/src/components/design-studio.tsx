import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Inbox, Layers, Moon, MoreHorizontal, PanelLeftClose, Search, Send, ShieldCheck, SlidersHorizontal, Sparkles, Sun, X } from "lucide-react";
import { Link } from "react-router";
import { Dialog } from "radix-ui";
import { MailboxAssistant } from "./mailbox-assistant";
import { PaneResize } from "./pane-resize";
import { TopicOriginal, TopicOverview, topicMails } from "./topic-overview";
import "@/tokens/design-studio.css";
import "@/tokens/mailbox-assistant.css";
import "@/tokens/design-density.css";
import "@/tokens/topic-workspace.css";
import { recordDesignAudit } from "@/lib/design-audit";
import "@/tokens/workspace-refinements.css";

const skins = [{ id: "paper", name: "纸与墨", subtitle: "Paper & ink" }, { id: "precision", name: "精密", subtitle: "Precision" }, { id: "mineral", name: "矿物", subtitle: "Mineral" }] as const;
type Skin = typeof skins[number]["id"];
const examples = [
  { initials: "ML", company: "Aurora Compute", contact: "Mikko Laine", email: "mikko@aurora.example", city: "赫尔辛基 · 芬兰", subject: "Helsinki DC · 2U 服务器采购", preview: "Please revise the quantity to 32 units…", product: "2U 机架服务器", model: "SYS-6029U-TR4", quantity: "32", old: "48", unit: "台", time: "09:42", tag: "数量变更", tone: "ochre", spec: "Dual Xeon E5-2680 v4 · 128 GB ECC · 4 × 3.84 TB SSD", body: "Thanks for the proposal. After reviewing our expansion plan, please revise the quantity from 48 to 32 units. The configuration remains the same. Refurbished units are acceptable if tested.", request: "Please quote CIF Helsinki with a 12-month warranty. Could you confirm availability and your earliest delivery date?", attachment: "Helsinki_DC_specification.xlsx" },
  { initials: "OH", company: "Gulf Edge Systems", contact: "Omar Haddad", email: "omar@gulfedge.example", city: "迪拜 · 阿联酋", subject: "HGX H200 · GPU 集群扩容", preview: "We are sourcing four 8-GPU systems…", product: "HGX H200 8-GPU 系统", model: "SYS-821GE-TNHR", quantity: "4", old: "", unit: "台", time: "09:18", tag: "新询盘", tone: "lilac", spec: "8 × NVIDIA H200 · Dual CPU · Redundant PSU", body: "We are sourcing four HGX H200 8-GPU systems for our Dubai facility. Please include the complete configuration and available warranty options.", request: "Could you share your current availability and lead time? Delivery address will follow after quotation.", attachment: "GPU_cluster_requirements.xlsx" },
  { initials: "王", company: "深圳华芯系统集成", contact: "王婷", email: "wang@huaxin.example", city: "深圳 · 中国", subject: "DDR5 RDIMM · 200 条现货询价", preview: "请提供原厂 64GB DDR5 的含税报价。", product: "DDR5 ECC RDIMM", model: "64GB · 4800 MT/s", quantity: "200", old: "", unit: "条", time: "08:56", tag: "待报价", tone: "rose", spec: "64 GB DDR5 · 4800 MT/s · ECC RDIMM · 原厂", body: "你好，我们需要 200 条原厂 64GB DDR5 4800 ECC RDIMM，用于客户服务器升级。请确认是否全新原包，并提供品牌和完整料号。", request: "请提供含税报价、质保条款和预计交期，送至深圳。谢谢。", attachment: "内存采购清单.xlsx" },
  { initials: "JW", company: "Rheinwerk Datentechnik", contact: "Jonas Weber", email: "jonas@rheinwerk.example", city: "杜塞尔多夫 · 德国", subject: "Enterprise SSD · 500 pcs", preview: "Looking for tested enterprise SSDs…", product: "企业级 SATA SSD", model: "3.84 TB · SATA", quantity: "500", old: "", unit: "片", time: "昨天", tag: "待报价", tone: "sage", spec: "3.84 TB · SATA · Health ≥ 90% · Tested", body: "We are looking for 500 tested enterprise SATA SSDs, 3.84 TB. Used or refurbished stock is acceptable, with drive health at least 90%.", request: "Please provide a quotation and a sample health report. Can you offer a warranty?", attachment: "SSD_requirements.xlsx" },
  { initials: "DK", company: "Strait Managed Services", contact: "Daniel Koh", email: "daniel@strait.example", city: "新加坡", subject: "Re: Q-2609 · 替代型号确认", preview: "Is there a replacement for the EOL model?", product: "2U 服务器替代方案", model: "SYS-6029U-TR4", quantity: "5", old: "", unit: "台", time: "昨天", tag: "待跟进", tone: "slate", spec: "2U · 原型号 EOL · 待确认替代配置", body: "Thank you for letting us know the original model is EOL. Can you still supply five units, or suggest an equivalent replacement?", request: "We would appreciate an updated quotation with the differences clearly noted.", attachment: "Original_configuration.xlsx" },
];

// More varied fictional inquiries make density review representative of a working inbox.
examples.push(
  { initials: "AR", company: "Instituto de Computação", contact: "Ana Ribeiro", email: "ana@instituto.example", city: "圣保罗 · 巴西", subject: "RTX 6000 Ada · 3 台工作站", preview: "Please quote three GPU workstations.", product: "GPU 工作站", model: "RTX 6000 Ada", quantity: "3", old: "", unit: "台", time: "昨天", tag: "新询盘", tone: "rose", spec: "RTX 6000 Ada · 128 GB RAM · 2 TB NVMe", body: "We need three workstations with RTX 6000 Ada GPUs, 128 GB RAM and 2 TB NVMe storage for our research lab.", request: "Please provide pricing and shipping options to São Paulo.", attachment: "Workstation_spec.xlsx" },
  { initials: "ES", company: "Baltic Rack AB", contact: "Erik Svensson", email: "erik@baltic.example", city: "斯德哥尔摩 · 瑞典", subject: "2U 存储节点 · 24 盘位", preview: "Could you quote eight storage nodes?", product: "2U 存储节点", model: "24-bay · NVMe", quantity: "8", old: "", unit: "台", time: "昨天", tag: "待报价", tone: "ochre", spec: "2U · 24 bays · NVMe · Dual PSU", body: "Could you quote eight 2U storage nodes with 24 NVMe bays and redundant power supplies?", request: "Please include supported drive models and warranty details.", attachment: "Storage_node_spec.xlsx" },
  { initials: "FA", company: "MyTel Infrastructure", contact: "Farah Aziz", email: "farah@mytel.example", city: "吉隆坡 · 马来西亚", subject: "Supermicro B300 · 配置确认", preview: "Two systems for our AI infrastructure.", product: "B300 GPU 服务器", model: "Supermicro B300", quantity: "2", old: "", unit: "台", time: "9/17", tag: "待跟进", tone: "sage", spec: "B300 · Build-to-order · Configuration pending", body: "We are planning to purchase two Supermicro B300 systems. Could you help us confirm the supported configuration?", request: "Please send the specification sheet and estimated lead time.", attachment: "B300_requirements.xlsx" },
  { initials: "CF", company: "Andes Datos SpA", contact: "Camila Fuentes", email: "camila@andes.example", city: "圣地亚哥 · 智利", subject: "DDR4 32GB · 600 条报价请求", preview: "Looking for ECC registered memory.", product: "DDR4 ECC RDIMM", model: "32GB · 3200 MT/s", quantity: "600", old: "", unit: "条", time: "9/17", tag: "待报价", tone: "slate", spec: "32 GB · DDR4-3200 · ECC RDIMM", body: "We are looking for 600 pieces of 32GB DDR4-3200 ECC registered memory. Please quote new and tested used options separately.", request: "Please include freight to Santiago and available warranty.", attachment: "Memory_RFQ.xlsx" },
  { initials: "BO", company: "Savanna Net Ltd", contact: "Brian Otieno", email: "brian@savanna.example", city: "内罗毕 · 肯尼亚", subject: "1U 服务器 · 预算方案", preview: "Ten servers under USD 800 per unit.", product: "1U 服务器", model: "1U · 型号待定", quantity: "10", old: "", unit: "台", time: "9/16", tag: "新询盘", tone: "sage", spec: "1U · Budget USD 800 / unit · Model pending", body: "We need ten 1U servers, with a budget of USD 800 per unit. Refurbished options are welcome.", request: "Please recommend a suitable configuration and advise shipping costs.", attachment: "Server_budget.xlsx" },
  { initials: "NT", company: "VinaParts Manufacturing", contact: "Nguyen Thi", email: "nguyen@vinaparts.example", city: "海防 · 越南", subject: "32GB DDR4 UDIMM · 1,000 条", preview: "Please confirm ECC UDIMM availability.", product: "DDR4 ECC UDIMM", model: "32GB · DDR4", quantity: "1,000", old: "", unit: "条", time: "9/16", tag: "待报价", tone: "lilac", spec: "32 GB · DDR4 · ECC UDIMM · Not RDIMM", body: "Please quote 1,000 pieces of 32GB DDR4 ECC UDIMM memory. We require unbuffered modules, not RDIMMs.", request: "Please confirm the exact part number before quoting.", attachment: "UDIMM_request.xlsx" },
  { initials: "JP", company: "Hanbit Cloud", contact: "Jin Park", email: "jin@hanbit.example", city: "首尔 · 韩国", subject: "L40S 服务器 · 数量调整", preview: "Please increase the order to 16 systems.", product: "4-GPU L40S 服务器", model: "4 × L40S", quantity: "16", old: "12", unit: "台", time: "9/15", tag: "数量变更", tone: "rose", spec: "4 × L40S · Dual CPU · Configuration unchanged", body: "Please increase the quantity from 12 to 16 systems. The four-GPU L40S configuration remains unchanged.", request: "Could you confirm whether the previous unit price still applies?", attachment: "L40S_original_spec.xlsx" },
);

function makeReply(item: typeof examples[number]) {
  return `Dear ${item.contact.split(" ")[0]},\n\nThank you for ${item.old ? "the update. We have noted the revised quantity of" : "your inquiry for"} ${item.quantity} ${item.unit === "台" ? "units" : "pieces"} of ${item.model}.\n\nWe are checking availability and lead time for your requested configuration and will get back to you with a formal quotation.\n\nCould you confirm your preferred delivery date?\n\nBest regards,\nLarry`;
}

export function DesignStudio() {
  const [skin, setSkin] = useState<Skin>("paper");
  const [dark, setDark] = useState(false);
  const [compact, setCompact] = useState(true);
  const [selected, setSelected] = useState(0);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"inbox" | "leads">("inbox");
  const [filter, setFilter] = useState("全部询盘");
  const [mobileList, setMobileList] = useState(false);
  const [confirmed, setConfirmed] = useState<number[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [compose, setCompose] = useState(false);
  const [source, setSource] = useState<"quantity" | "attachment" | "about" | "shortcuts" | null>(null);
  const [toast, setToast] = useState("");
  const [history, setHistory] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [listHidden, setListHidden] = useState(false);
  const [activeMailId, setActiveMailId] = useState("latest");
  const [overviewLast, setOverviewLast] = useState(false);
  const [widths, setWidths] = useState(() => {
    const fallback = { nav: 172, list: 300, assistant: 380 };
    try {
      const saved = JSON.parse(localStorage.getItem("mail2leads.design.widths") || "null");
      if (saved && Object.values(saved).every(value => typeof value === "number" && Number.isFinite(value))) return { nav: Math.max(140, Math.min(230, saved.nav || 172)), list: Math.max(220, Math.min(480, saved.list || 300)), assistant: Math.max(280, Math.min(520, saved.assistant || 380)) };
    } catch { /* Storage is optional in this prototype. */ }
    return fallback;
  });
  useEffect(() => { try { localStorage.setItem("mail2leads.design.widths", JSON.stringify(widths)); } catch { /* Private browsing may disallow persistence. */ } }, [widths]);
  const assistantTrigger = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const item = examples[selected];
  const topic = topicMails(item, selected);
  const activeMail = topic.find(mail => mail.id === activeMailId) ?? topic[topic.length - 1];
  const visible = examples.map((entry, index) => ({ ...entry, index })).filter(entry => `${entry.company} ${entry.subject} ${entry.model}`.toLowerCase().includes(query.toLowerCase()) && (filter !== "待确认" || !confirmed.includes(entry.index)) && (view !== "leads" || confirmed.includes(entry.index)));
  const draft = drafts[selected] ?? makeReply(item);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (compose) editorRef.current?.focus();
  }, [compose, selected]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      if (source || target.closest("input, textarea, select, [contenteditable]")) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "/") { event.preventDefault(); searchRef.current?.focus(); }
      if (event.key === "r") setCompose(true);
      if (event.key === "?") setSource("shortcuts");
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        const current = visible.findIndex(entry => entry.index === selected);
        const next = visible[Math.max(0, Math.min(visible.length - 1, current + (event.key === "j" ? 1 : -1)))];
        if (next) { setSelected(next.index); setActiveMailId("latest"); setCompose(false); }
      }
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [visible, selected, source]);

  function choose(index: number) { setSelected(index); setActiveMailId("latest"); setCompose(false); setMobileList(false); setHistory(false); }
  function confirm() { setConfirmed(value => value.includes(selected) ? value : [...value, selected]); setToast("已在原型中确认为线索，可在线索列表查看"); }

  return (
    <div className="ds" data-skin={skin} data-mode={dark ? "dark" : "light"} data-density={compact ? "compact" : "comfortable"} onClickCapture={event => { const target = (event.target as HTMLElement).closest("button, a, summary"); if (target) void recordDesignAudit("ui.click", { target: target.getAttribute("aria-label") || target.textContent?.slice(0, 200), topic: selected }).catch(() => {}); }}>
      <div className="ds-studio">
        <div className="ds-studio-label"><span className="ds-live-dot" /> DESIGN STUDY <span className="ds-studio-version">02 — 高密度邮件工作台</span><Link to="/mail">打开真实邮箱 ↗</Link></div>
        <div className="ds-skin-options" aria-label="视觉方案">{skins.map(option => <button key={option.id} aria-pressed={skin === option.id} onClick={() => setSkin(option.id)}><i className={`ds-swatch ds-swatch-${option.id}`} />{option.name}<span>{option.subtitle}</span></button>)}</div>
        <div className="ds-studio-tools"><button aria-label={dark ? "切换亮色" : "切换暗色"} onClick={() => setDark(!dark)}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button><button className="ds-density-switch" aria-label="切换紧凑密度" aria-pressed={compact} onClick={() => setCompact(!compact)}><SlidersHorizontal size={16} /><span>{compact ? "紧凑" : "舒展"}</span></button><Link to="/">原版 <ArrowUpRight size={13} /></Link></div>
      </div>

      <div className={`ds-app ds-resizable ${assistantOpen ? "ds-with-assistant" : ""} ${listHidden ? "ds-list-hidden" : ""}`} style={{ "--ds-nav-width": `${widths.nav}px`, "--ds-list-width": `${widths.list}px`, "--ds-assistant-width": `${widths.assistant}px` } as CSSProperties}>
        <aside className="ds-sidebar">
          <div className="ds-brand"><span className="ds-brandmark"><Layers size={20} /></span><span>aimail<span className="ds-brand-caption">A quieter way to work.</span></span></div>
          <div className="ds-workspace"><span className="ds-workspace-icon">G</span><div>Glocal Trading<small>sales@ · 设计示例</small></div><ChevronDown size={13} /></div>
          <div className="ds-nav-label">工作空间</div>
          <button className={`ds-nav ${assistantOpen ? "is-active" : ""}`} onClick={() => setAssistantOpen(!assistantOpen)} aria-expanded={assistantOpen}><Sparkles size={17} />问邮箱</button>
          <button className={`ds-nav ${view === "inbox" ? "is-active" : ""}`} onClick={() => { setView("inbox"); setFilter("全部询盘"); setMobileList(true); }}><Inbox size={17} />收件箱 <span>{examples.length}</span></button>
          <button className={`ds-nav ${view === "leads" ? "is-active" : ""}`} onClick={() => { setView("leads"); setFilter("全部询盘"); setMobileList(true); if (confirmed.length) choose(confirmed[0]); }}><Layers size={17} />已确认线索<span>{confirmed.length}</span></button>
          <div className="ds-nav-label ds-later">处理队列</div>
          <button className={`ds-nav ds-subnav ${filter === "待确认" ? "is-active" : ""}`} onClick={() => { setFilter("待确认"); setView("inbox"); setMobileList(true); }}><span className="ds-status-dot" />待确认<span>{examples.length - confirmed.length}</span></button>
          <div className="ds-sidebar-note"><span className="ds-mini-rule" /><p>每条需求，都有来处。<br />每次承诺，由你决定。</p></div>
          <div className="ds-sidebar-bottom"><button onClick={() => setSource("shortcuts")}><CircleHelp size={16} />快捷键 <kbd>?</kbd></button><div className="ds-account"><span className="ds-avatar ds-avatar-self">L</span><div>Larry<small>销售工作台</small></div><span className="ds-online" /></div></div>
          <PaneResize label="调整导航栏宽度" value={widths.nav} min={140} max={230} onChange={nav => setWidths(previous => ({ ...previous, nav }))} onReset={() => setWidths(previous => ({ ...previous, nav: 172 }))} />
        </aside>

        <section className={`ds-mail-list ${mobileList ? "ds-mobile-show" : ""} ${listHidden ? "is-collapsed" : ""}`} aria-label="询盘列表">
          {listHidden && <button className="ds-list-restore" aria-label="展开邮件列表" onClick={() => setListHidden(false)}><PanelLeftClose size={17} /><span>{visible.length}</span></button>}
          <header className="ds-list-heading"><h1>{view === "leads" ? "已确认线索" : "收件箱"}<span>{visible.length}</span></h1><button aria-label="收起邮件列表" onClick={() => { setListHidden(true); setMobileList(false); }}><PanelLeftClose size={16} /></button></header>
          <div className="ds-search"><Search size={15} /><input ref={searchRef} aria-label="搜索询盘" placeholder="搜索客户、型号、主题" value={query} onChange={event => setQuery(event.target.value)} /><kbd>/</kbd></div>
          <div className="ds-list-tabs"><button className={filter === "全部询盘" ? "is-active" : ""} onClick={() => setFilter("全部询盘")}>全部询盘</button><button className={filter === "待确认" ? "is-active" : ""} onClick={() => setFilter("待确认")}>待确认</button><span>最新优先 <ArrowDown size={11} /></span></div>
          <div className="ds-list-scroll"><div className="ds-day-label">最近往来</div>{visible.map(entry => <button className={`ds-mail-row ${selected === entry.index ? "is-selected" : ""}`} key={entry.index} onClick={() => choose(entry.index)} aria-current={selected === entry.index ? "true" : undefined}>
            <div className="ds-mail-row-top"><span className={`ds-avatar ds-avatar-${entry.tone}`}>{entry.initials}</span><strong>{entry.company}</strong><time>{entry.time}</time></div>
            <div className="ds-mail-row-content"><h3>{entry.subject}</h3><p>{entry.preview}</p><div className="ds-row-meta"><span className={entry.old ? "ds-change-label" : ""}>{confirmed.includes(entry.index) ? "已确认" : entry.tag}</span><span>{entry.quantity} {entry.unit} <span className="ds-meta-dot">·</span> {entry.city.split(" · ")[0]}</span></div></div>
          </button>)}{!visible.length && <div className="ds-empty"><Inbox size={26} /><h3>{view === "leads" ? "让第一条线索落在这里" : "没有匹配的询盘"}</h3><p>{view === "leads" ? "在询盘详情核对需求后，点击「确认为线索」。" : "试试客户名称或产品型号。"}</p><button onClick={() => { setView("inbox"); setFilter("全部询盘"); setQuery(""); }}>查看全部询盘 <ArrowRight size={14} /></button></div>}</div>
          <footer className="ds-list-footer"><ShieldCheck size={13} />人工确认后，才进入线索<span>示例数据</span></footer>
          <PaneResize label="调整邮件列表宽度" value={widths.list} min={220} max={480} onChange={list => setWidths(previous => ({ ...previous, list }))} onReset={() => setWidths(previous => ({ ...previous, list: 300 }))} />
        </section>

        <main className={`ds-detail ${mobileList ? "ds-mobile-hide" : ""}`}>
          <header className="ds-detail-toolbar"><div><button className="ds-back" aria-label="返回询盘列表" onClick={() => setMobileList(true)}><ArrowLeft size={17} /></button><span>询盘</span><ChevronRight size={13} /><span>{item.company}</span></div><div><span className="ds-index">{selected + 1} / {examples.length}</span><button aria-label="上一封" disabled={selected === 0} onClick={() => choose(selected - 1)}><ChevronLeft size={16} /></button><button aria-label="下一封" disabled={selected === examples.length - 1} onClick={() => choose(selected + 1)}><ChevronRight size={16} /></button><button aria-label="原型说明" onClick={() => setSource("about")}><MoreHorizontal size={19} /></button><button ref={assistantTrigger} className="ds-ask-trigger" aria-expanded={assistantOpen} onClick={() => setAssistantOpen(!assistantOpen)}><Sparkles size={15} />问邮箱</button></div></header>
          <div className="ds-detail-scroll" key={selected}>
            <div className="ds-content">
              <div className="ds-eyebrow"><span className="ds-status-dot" />{confirmed.includes(selected) ? "已确认线索" : "待你确认"}<span>INQUIRY / {String(selected + 1).padStart(3, "0")}</span></div>
              <h2 className="ds-subject">{item.subject}</h2>
              <div className="ds-customer"><span className={`ds-avatar ds-avatar-${item.tone}`}>{item.initials}</span><div><strong>{item.contact}</strong><span>{item.company} <span className="ds-meta-dot">·</span> {item.city}</span></div><button onClick={() => setHistory(!history)} aria-expanded={history}>{selected === 0 ? "3 次历史往来" : "客户资料"}<ChevronDown size={13} /></button></div>
              {history && <div className="ds-history"><strong>客户往来 · 示例</strong><p>{selected === 0 ? "9 月 12 日 · 首次询价 48 台服务器 → 9 月 16 日 · 我方提供方案 → 今天 · 客户调整为 32 台。" : `${item.contact} · ${item.email}。当前示例只提供这条询盘。`}</p></div>}

              <div className={`ds-topic-stack ${overviewLast ? "ds-overview-last" : ""}`} onDragOver={event => { if (event.dataTransfer.types.includes("application/x-mail2leads-panel")) event.preventDefault(); }} onDrop={event => { const panel = event.dataTransfer.getData("application/x-mail2leads-panel"); if (!panel) return; event.preventDefault(); const rect = event.currentTarget.getBoundingClientRect(); const bottom = event.clientY > rect.top + rect.height / 2; setOverviewLast(panel === "topic" ? bottom : !bottom); }}>
              <TopicOverview key={selected} mails={topic} customer={item} activeId={activeMail.id} onRead={setActiveMailId} last={overviewLast} onMove={() => setOverviewLast(!overviewLast)} recap={selected === 0 ? "客户将数量从 48 台调整为 32 台，配置不变。我方已提供配置方案，最终报价与交期仍待确认。" : selected === 1 ? "客户已回复我方的数量追问：需要 4 台八卡 H200 系统。送货地址将于报价后提供，库存、交期与质保方案待我方回复。" : selected === 3 ? "该话题目前有 1 封来信：客户采购 500 片 3.84 TB 企业级 SATA SSD，接受二手或翻新，要求已测试且健康度至少 90%。客户同时索取报价、健康报告样本和质保说明；目前邮件中没有明确预算、交付日期或我方回复。" : `本话题目前有 ${topic.length} 封示例邮件，最新需求为 ${item.quantity} ${item.unit}${item.product}。${item.old ? `数量由 ${item.old} 调整为 ${item.quantity}，其余配置不变。` : `规格涉及 ${item.spec}。`} 尚未从这份示例中取得已确认的成交价格或交付日期。`}>
              <section className="ds-brief" aria-label="专题最新需求摘要">
                <div className="ds-section-title"><span>最新需求与待办</span><button onClick={() => setSource("about")}><ShieldCheck size={13} />AI 整理 · 待核对 <ChevronRight size={12} /></button></div>
                <div className="ds-brief-title"><h3>{item.product}</h3><button className="ds-quantity" onClick={() => setSource("quantity")} aria-label="查看数量来源">{item.old && <del>{item.old}</del>}{item.old && <ArrowRight size={15} />}<strong>{item.quantity}</strong><span>{item.unit}</span><ArrowUpRight size={13} /></button></div>
                <p className="ds-spec">{item.spec}</p>
                <div className="ds-facts"><div><span>交付地点</span><strong>{item.city.split(" · ")[0]}</strong></div><div><span>{selected === 0 ? "贸易条款" : "产品型号"}</span><strong>{selected === 0 ? "CIF · 含运保费" : item.model}</strong></div><div><span>{selected === 0 ? "成色 / 质保" : "交期"}</span><strong>{selected === 0 ? "接受翻新 / 12 个月" : "待确认"}</strong></div></div>
                <div className="ds-attention"><span className="ds-attention-dot" /><span>{item.old ? <>本次变更：数量从 <b>{item.old}</b> 调整为 <b>{item.quantity}</b>，其余配置不变。</> : "待补充：客户尚未明确期望交付日期。"}</span><button onClick={() => setSource("quantity")}>看原文 <ArrowUpRight size={12} /></button></div>
              </section>
              </TopicOverview>
              <TopicOriginal mail={activeMail} onAttachment={() => setSource("attachment")} />
              </div>

              {!compose ? <div className="ds-next-action"><div><span className="ds-next-icon"><ArrowRight size={18} /></span><div><strong>{confirmed.includes(selected) ? "需求已确认，准备回复" : "核对需求，推进这笔询盘"}</strong><p>{confirmed.includes(selected) ? "让客户知道你正在确认库存与交期。" : "确认后进入线索，回复由你审阅并发出。"}</p></div></div><button className="ds-btn ds-btn-primary" onClick={() => setCompose(true)}><Send size={14} />起草回复 <kbd>R</kbd></button></div> : <section className="ds-composer" aria-label="回复编辑器"><header><span><Send size={15} />回复 {item.contact}</span><button aria-label="收起回复，保留草稿" onClick={() => setCompose(false)}><X size={16} /></button></header><div className="ds-to">收件人 <span>{item.email}</span><span>草稿 · 示例</span></div><textarea ref={editorRef} aria-label="回复正文" value={draft} onChange={event => setDrafts({ ...drafts, [selected]: event.target.value })} /><footer><span><ShieldCheck size={13} />由你审阅，按你的意思回复</span><button className="ds-btn ds-btn-primary" disabled={!draft.trim()} onClick={() => { setToast("演示发送完成；没有发送真实邮件。草稿仍保留。"); setCompose(false); }}><Send size={14} />模拟发送</button></footer></section>}
              <div className="ds-prototype-note">交互设计原型 · 内容为虚构示例 · 不连接真实邮箱</div>
            </div>
          </div>
          <footer className="ds-actionbar"><span><ShieldCheck size={15} />{confirmed.includes(selected) ? "已由 Larry 确认 · 原型记录" : "AI 提取为建议，请核对后确认"}</span><button className={`ds-btn ${confirmed.includes(selected) ? "ds-btn-confirmed" : "ds-btn-secondary"}`} disabled={confirmed.includes(selected)} onClick={confirm}><Check size={15} />{confirmed.includes(selected) ? "已确认为线索" : "确认为线索"}</button></footer>
          {assistantOpen && <PaneResize label="调整跨专题助手宽度" value={widths.assistant} min={280} max={520} reverse onChange={assistant => setWidths(previous => ({ ...previous, assistant }))} onReset={() => setWidths(previous => ({ ...previous, assistant: 380 }))} />}
        </main>
        <MailboxAssistant open={assistantOpen} examples={examples} selected={selected} confirmed={confirmed} onClose={() => { setAssistantOpen(false); assistantTrigger.current?.focus(); }} onNavigate={index => { setView("inbox"); setFilter("全部询盘"); setQuery(""); choose(index); if (window.matchMedia("(max-width: 760px)").matches) setAssistantOpen(false); }} />
      </div>
      <div className="ds-toast" role="status" aria-live="polite">{toast && <span><Check size={16} />{toast}</span>}</div>
      <Dialog.Root open={source !== null} onOpenChange={open => { if (!open) setSource(null); }}><Dialog.Portal><Dialog.Overlay className="ds-modal-overlay" /><Dialog.Content className="ds ds-modal" data-skin={skin} data-mode={dark ? "dark" : "light"}>
        <div className="ds-modal-header"><Dialog.Title>{source === "quantity" ? "回到原文核对" : source === "attachment" ? "附件预览" : source === "shortcuts" ? "少一点鼠标，多一点从容" : "关于这份需求速览"}</Dialog.Title><Dialog.Close aria-label="关闭"><X size={18} /></Dialog.Close></div>
        <Dialog.Description className="ds-modal-description">{source === "quantity" ? `${item.contact} · 9 月 19 日 · 数量来源示例` : source === "attachment" ? item.attachment : source === "shortcuts" ? "输入正文或搜索时，不会触发这些快捷键。" : "这是一份可操作的视觉与交互提案。"}</Dialog.Description>
        {source === "quantity" && <><div className="ds-source-quote">{item.old ? <>Please revise the quantity from <del>{item.old}</del> to <mark>{item.quantity} units</mark>. The configuration remains the same.</> : <>{item.body}</>}</div><p className="ds-source-note"><ShieldCheck size={16} />此处展示预设的来源定位。正式接入需要字段级原文引用；数字在原文出现，不等于语义已验证。</p></>}
        {source === "attachment" && <><div className="ds-attachment-table"><div><span>字段</span><span>示例内容</span></div><div><span>Product</span><strong>{item.product}</strong></div><div><span>Model</span><strong>{item.model}</strong></div><div><span>Quantity</span><strong>{item.old || item.quantity} {item.unit}</strong></div><div><span>Configuration</span><strong>{item.spec}</strong></div></div><p className="ds-source-note">{item.old ? "附件保留最初的 48 台要求；最新邮件调整为 32 台，确认时以最新往来为依据。" : "这是交互原型的示例附件内容。"}</p></>}
        {source === "shortcuts" && <div className="ds-shortcuts">{[["下一封 / 上一封", "J / K"], ["搜索询盘", "/"], ["打开回复", "R"], ["查看快捷键", "?"], ["关闭弹窗", "Esc"]].map(([label, key]) => <div key={key}><span>{label}</span><kbd>{key}</kbd></div>)}</div>}
        {source === "about" && <div className="ds-about"><p>三套皮肤使用同一份内容和交互。你可以切换亮暗模式、调整密度、搜索和切换客户、核对数量来源、查看附件、确认线索和编辑回复。</p><p>所有内容为固定的虚构示例，没有调用模型，也不会发送真实邮件。刷新后，原型里的确认状态和草稿会重置。</p><p>正式产品将保留模型、任务版本、生成时间与原邮件的可追溯关系。这里先验证它们如何在界面中呈现。</p></div>}
      </Dialog.Content></Dialog.Portal></Dialog.Root>
    </div>
  );
}
