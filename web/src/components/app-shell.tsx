import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { CircleUserRound, Inbox, Maximize2, Menu, Minimize2, PanelLeftClose, PanelLeftOpen, List, PanelRightClose, PanelRightOpen, X } from "lucide-react";
import { PaneResize } from "./pane-resize";
import "@/tokens/mail-layout.css";
import { cn } from "@/lib/cn";
import { AccountMenu } from "./account-menu";
import "@/tokens/outlook-workspace.css";

const LAYOUT_KEY = "aimail-inbox-layout";
const DEFAULT_WIDTH = 360;
const DEFAULT_NAV_WIDTH = 220;
const CUSTOMER_LAYOUT_KEY = "aimail-customer-layout";
const DEFAULT_CUSTOMER_WIDTH = 320;
const MIN_READER_WIDTH = 360;

function loadCustomerLayout(initiallyCollapsed = false): { width: number; collapsed: boolean } {
  try {
    const saved = JSON.parse(localStorage.getItem(CUSTOMER_LAYOUT_KEY) ?? "{}");
    return {
      width: Number.isFinite(saved.width) ? Math.max(280, Math.min(520, saved.width)) : DEFAULT_CUSTOMER_WIDTH,
      collapsed: typeof saved.collapsed === "boolean" ? saved.collapsed : initiallyCollapsed,
    };
  } catch { return { width: DEFAULT_CUSTOMER_WIDTH, collapsed: initiallyCollapsed }; }
}
function loadLayout(): { width: number } {
  try {
    const value = JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? "{}");
    return {
      width: Number.isFinite(value.width) ? Math.max(260, Math.min(600, value.width)) : DEFAULT_WIDTH,
    };
  } catch { return { width: DEFAULT_WIDTH }; }
}

/** Shared brand, location and account bar on every application page. */
export function ApplicationHeader({ title = "邮箱", onNavigation, navigation, modelControl, searchControl }: {
  title?: string; onNavigation?: () => void; navigation?: ReactNode; modelControl?: ReactNode; searchControl?: ReactNode;
}) {
  return <div className="mail-topbar">
    {onNavigation && <button className="mail-topbar-menu mail-icon-button" type="button" aria-label="展开主导航" onClick={onNavigation}><Menu size={18} /></button>}
    <a href="/" className="mail-product-mark" aria-label="Aimail 首页"><span><Inbox size={17} /></span>aimail</a>
    {searchControl && <div className="mail-global-search">{searchControl}</div>}
    {modelControl}
    <span className="mail-topbar-location">{title}</span>
    {navigation}
    <AccountMenu />
  </div>;
}

/** 三栏壳:侧栏 | 列表 | 详情;或 侧栏 | 主区。手机上列表与详情二选一,由路由决定。 */
export function AppShell({
  sidebar,
  list,
  detail,
  main,
  assistant,
  assistantOpen = false,
  onFullscreen,
  showDetail = false,
  customer,
  title,
  modelControl,
  searchControl,
  toolbar,
  rail,
  customerInitiallyCollapsed = false,
}: {
  sidebar: ReactNode;
  list?: ReactNode;
  detail?: ReactNode;
  main?: ReactNode;
  assistant?: ReactNode;
  assistantOpen?: boolean;
  onFullscreen?: () => void;
  showDetail?: boolean;
  readerKey?: string;
  customer?: ReactNode;
  title?: string;
  modelControl?: ReactNode;
  searchControl?: ReactNode;
  toolbar?: ReactNode;
  rail?: ReactNode;
  customerInitiallyCollapsed?: boolean;
}) {
  const [layout, setLayout] = useState(loadLayout);
  const [hidden, setHidden] = useState(false);
  const [navigation, setNavigation] = useState(() => {
    try { const saved = JSON.parse(localStorage.getItem("aimail-navigation-layout") ?? "{}"); return { width: Number.isFinite(saved.width) ? Math.max(180, Math.min(280, saved.width)) : DEFAULT_NAV_WIDTH, collapsed: saved.collapsed === true }; }
    catch { return { width: DEFAULT_NAV_WIDTH, collapsed: false }; }
  });
  const [customerLayout, setCustomerLayout] = useState(() => loadCustomerLayout(customerInitiallyCollapsed));
  const [customerOpen, setCustomerOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [navigationOverlay, setNavigationOverlay] = useState(false);
  const [viewport, setViewport] = useState(window.innerWidth);
  const readerFocused = focused && showDetail && !assistantOpen;
  const compactNavigation = viewport < 768;
  const customerInline = viewport >= 1300;
  const navigationVisible = compactNavigation ? navigationOverlay : !navigation.collapsed;
  const collapsed = showDetail && hidden;
  // Auxiliary panes share a fixed viewport budget; the reader owns the remaining width.
  const customerGutter = customer && !readerFocused && customerInline && !customerLayout.collapsed ? 12 : 0;
  const paneGutters = rail ? viewport >= 768 ? 60 + customerGutter : 16 : 26;
  const availableWidth = Math.max(0, viewport - paneGutters - (rail && viewport >= 768 ? 52 : 0));
  const navigationSpace = readerFocused ? 0 : compactNavigation || navigation.collapsed ? 0 : navigation.width;
  const listSpace = readerFocused ? 0 : collapsed ? 0 : 260;
  const customerMax = Math.max(280, Math.min(520, availableWidth - navigationSpace - listSpace - MIN_READER_WIDTH));
  const customerWidth = Math.min(customerLayout.width, customerMax);
  const customerVisible = Boolean(customer) && !readerFocused && (customerInline ? !customerLayout.collapsed : customerOpen);
  const customerSpace = customerVisible && customerInline ? customerWidth : 0;
  const listMax = Math.max(260, Math.min(600, availableWidth - navigationSpace - customerSpace - MIN_READER_WIDTH));
  const listWidth = Math.min(layout.width, listMax);
  const toggleCustomer = () => {
    if (readerFocused) {
      setFocused(false);
      if (customerInline) setCustomerLayout(value => ({ ...value, collapsed: false }));
      else setCustomerOpen(true);
      return;
    }
    if (customerInline) setCustomerLayout(value => ({ ...value, collapsed: !value.collapsed }));
    else setCustomerOpen(value => !value);
  };
  useEffect(() => {
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch { /* 私密浏览仍可调整当前布局。 */ }
  }, [layout]);
  useEffect(() => { try { localStorage.setItem("aimail-navigation-layout", JSON.stringify(navigation)); } catch { /* 当前布局仍可用。 */ } }, [navigation]);
  useEffect(() => { try { localStorage.setItem(CUSTOMER_LAYOUT_KEY, JSON.stringify(customerLayout)); } catch { /* 当前布局仍可用。 */ } }, [customerLayout]);
  useEffect(() => {
    const resized = () => setViewport(window.innerWidth);
    window.addEventListener("resize", resized);
    return () => window.removeEventListener("resize", resized);
  }, []);
  useEffect(() => {
    if (!navigationOverlay) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setNavigationOverlay(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [navigationOverlay]);
  const expand = () => setHidden(false);
  const layoutControls = showDetail && <div className="mail-reader-layout-controls" aria-label="阅读布局">
    {!readerFocused && !navigationVisible && <button type="button" aria-label="展开左侧导航" aria-expanded={false} onClick={() => { if (compactNavigation) setNavigationOverlay(true); else setNavigation(value => ({ ...value, collapsed: false })); }}><PanelLeftOpen size={16} /><span>邮箱导航</span></button>}
    {!readerFocused && collapsed && <button type="button" aria-label="展开邮件列表" aria-expanded={false} onClick={expand}><List size={16} /><span>邮件列表</span></button>}
    <button type="button" aria-label={readerFocused ? "退出邮件全屏" : "邮件全屏"} aria-pressed={readerFocused} onClick={() => { if (!readerFocused) onFullscreen?.(); setFocused(!readerFocused); }} title={readerFocused ? "恢复之前的阅读布局" : "隐藏两侧面板，展开正文"}>{readerFocused ? <Minimize2 size={16} /> : <Maximize2 size={16} />}<span>{readerFocused ? "退出邮件全屏" : "邮件全屏"}</span></button>
    {customer && <button className="mail-customer-toggle" type="button" onClick={toggleCustomer} aria-label={customerVisible ? "隐藏客户工作区" : "展开客户工作区"} aria-expanded={customerVisible} aria-controls="mail-customer-workspace">{customerVisible ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}<span>客户工作区</span><small>{customerVisible ? "已展开" : "已收起"}</small></button>}
  </div>;
  return (
    <div className={cn("mail-app-shell flex h-full min-h-0 w-full flex-col bg-canvas", Boolean(rail) && "mail-outlook-workspace", Boolean(customer) && "mail-customer-workspace", assistantOpen && "mail-assistant-open", readerFocused && "mail-reader-focused")}>
      <ApplicationHeader title={title ?? (main ? "工作台" : "邮箱")} onNavigation={() => { setFocused(false); if (compactNavigation) setNavigationOverlay(value => !value); else setNavigation(value => ({ ...value, collapsed: !value.collapsed })); }} modelControl={modelControl} searchControl={searchControl} />
      <div className="mail-app-panes flex min-h-0 flex-1">
        {rail && !readerFocused && rail}
        {compactNavigation && navigationOverlay && !readerFocused && <button type="button" className="mail-navigation-backdrop" aria-label="关闭导航抽屉" onClick={() => setNavigationOverlay(false)} /> }
        <div className="mail-navigation" hidden={readerFocused || !navigationVisible} data-compact={compactNavigation} data-collapsed={navigation.collapsed} data-overlay={navigationOverlay} style={{ "--mail-nav-width": `${navigation.width}px` } as CSSProperties}>
          <button className="mail-navigation-toggle" type="button" aria-label={navigationVisible ? "隐藏左侧导航" : "展开左侧导航"} onClick={() => { if (compactNavigation) setNavigationOverlay(value => !value); else setNavigation(value => ({ ...value, collapsed: !value.collapsed })); }}>{navigationVisible ? <PanelLeftClose size={17} strokeWidth={1.75} /> : <PanelLeftOpen size={17} strokeWidth={1.75} />}</button>
          <div className="mail-navigation-content" onClick={event => { if ((event.target as HTMLElement).closest("a")) setNavigationOverlay(false); }}>{sidebar}</div>
          {!navigation.collapsed && !compactNavigation && <PaneResize label="调整左侧导航宽度" value={navigation.width} min={180} max={280} onChange={width => setNavigation(value => ({ ...value, width }))} onReset={() => setNavigation(value => ({ ...value, width: DEFAULT_NAV_WIDTH }))} />}
        </div>
        {main ? (
          <main className="min-w-0 flex-1 overflow-y-auto">{main}</main>
        ) : (
          <>
            <section
              aria-label="列表"
              hidden={readerFocused}
              style={{ "--mail-list-width": `${listWidth}px` } as CSSProperties}
              className={cn(
                "mail-list-pane relative w-full min-h-0 shrink-0 flex-col border-r border-line bg-surface",
                collapsed && "mail-list-collapsed",
                showDetail ? "hidden" : "flex",
              )}
            >
              <div className="mail-list-content">
                <div className="mail-list-controls">
                  <span>收件箱</span>
                  <button type="button" aria-label="收起邮件列表" title="收起邮件列表" disabled={!showDetail} onClick={() => setHidden(true)}>
                    <PanelLeftClose size={17} />
                  </button>
                </div>
                {list}
              </div>
              <PaneResize label="调整邮件列表宽度" value={listWidth} min={260} max={listMax}
                onChange={width => setLayout(value => ({ ...value, width }))}
                onReset={() => setLayout(value => ({ ...value, width: DEFAULT_WIDTH }))} />
            </section>
            <main className={cn("mail-reader-pane min-w-0 flex-1 flex-col md:flex", showDetail ? "flex" : "hidden")}>
              {showDetail && <div className="mail-reader-toolbar">{toolbar}{layoutControls}</div>}
              {detail}
            </main>
            {customer && <aside id="mail-customer-workspace" className="mail-customer-pane" hidden={!customerVisible} data-open={customerOpen} aria-label="客户需求栏" style={{ "--mail-customer-width": `${customerWidth}px` } as CSSProperties}>
              {customerInline && <PaneResize label="调整正文与客户工作区宽度" value={customerWidth} min={280} max={customerMax} reverse edge="start" onChange={width => setCustomerLayout(value => ({ ...value, width }))} onReset={() => setCustomerLayout(value => ({ ...value, width: DEFAULT_CUSTOMER_WIDTH }))} />}
              <header><span><CircleUserRound size={17} strokeWidth={1.75} />客户工作区</span><button type="button" aria-label="收起客户工作区" title="收起客户工作区" onClick={() => { if (customerInline) setCustomerLayout(value => ({ ...value, collapsed: true })); else setCustomerOpen(false); }}><X size={17} strokeWidth={1.75} /></button></header>
              <div className="mail-customer-scroll">{customerVisible ? customer : null}</div>
            </aside>}
            {assistant}
          </>
        )}
      </div>
    </div>
  );
}
