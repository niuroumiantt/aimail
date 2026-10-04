import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { CircleUserRound, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { PaneResize } from "./pane-resize";
import "@/tokens/mail-layout.css";
import { cn } from "@/lib/cn";
import { AccountMenu } from "./account-menu";

const LAYOUT_KEY = "aimail-inbox-layout";
const DEFAULT_WIDTH = 352;
function loadLayout(): { width: number; autoHide: boolean } {
  try {
    const value = JSON.parse(localStorage.getItem(LAYOUT_KEY) ?? "{}");
    return {
      width: Number.isFinite(value.width) ? Math.max(260, Math.min(600, value.width)) : DEFAULT_WIDTH,
      autoHide: value.autoHide === true,
    };
  } catch { return { width: DEFAULT_WIDTH, autoHide: false }; }
}

/** 三栏壳:侧栏 | 列表 | 详情;或 侧栏 | 主区。手机上列表与详情二选一,由路由决定。 */
export function AppShell({
  sidebar,
  list,
  detail,
  main,
  assistant,
  assistantOpen = false,
  showDetail = false,
  readerKey = "",
  customer,
}: {
  sidebar: ReactNode;
  list?: ReactNode;
  detail?: ReactNode;
  main?: ReactNode;
  assistant?: ReactNode;
  assistantOpen?: boolean;
  showDetail?: boolean;
  readerKey?: string;
  customer?: ReactNode;
}) {
  const [layout, setLayout] = useState(loadLayout);
  const [hidden, setHidden] = useState(false);
  const [expandedFor, setExpandedFor] = useState<string>();
  const [navigation, setNavigation] = useState(() => {
    try { const saved = JSON.parse(localStorage.getItem("aimail-navigation-layout") ?? "{}"); return { width: Number.isFinite(saved.width) ? Math.max(180, Math.min(280, saved.width)) : 204, collapsed: saved.collapsed === true }; }
    catch { return { width: 204, collapsed: false }; }
  });
  const [customerOpen, setCustomerOpen] = useState(false);
  const [navigationOverlay, setNavigationOverlay] = useState(false);
  const compactNavigation = Boolean(customer) && window.innerWidth < 1300;
  const navigationVisible = compactNavigation ? navigationOverlay : !navigation.collapsed;
  const collapsed = showDetail && (hidden || (layout.autoHide && expandedFor !== readerKey));
  useEffect(() => {
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch { /* 私密浏览仍可调整当前布局。 */ }
  }, [layout]);
  useEffect(() => { try { localStorage.setItem("aimail-navigation-layout", JSON.stringify(navigation)); } catch { /* 当前布局仍可用。 */ } }, [navigation]);
  const expand = () => { setHidden(false); setExpandedFor(readerKey); };
  return (
    <div className={cn("mail-app-shell flex h-full min-h-0 w-full flex-col bg-canvas", Boolean(customer) && "mail-customer-workspace", assistantOpen && "mail-assistant-open")}>
      <AccountMenu />
      <div className="mail-app-panes flex min-h-0 flex-1">
        <div className="mail-navigation" data-collapsed={navigation.collapsed} data-overlay={navigationOverlay} style={{ "--mail-nav-width": `${navigation.width}px` } as CSSProperties}>
          <button className="mail-navigation-toggle" type="button" aria-label={navigationVisible ? "隐藏左侧导航" : "展开左侧导航"} onClick={() => { if (compactNavigation) setNavigationOverlay(value => !value); else setNavigation(value => ({ ...value, collapsed: !value.collapsed })); }}>{navigationVisible ? <PanelLeftClose size={17} strokeWidth={1.75} /> : <PanelLeftOpen size={17} strokeWidth={1.75} />}</button>
          <div className="mail-navigation-content">{sidebar}</div>
          {!navigation.collapsed && <PaneResize label="调整左侧导航宽度" value={navigation.width} min={180} max={280} onChange={width => setNavigation(value => ({ ...value, width }))} onReset={() => setNavigation(value => ({ ...value, width: 204 }))} />}
        </div>
        {main ? (
          <main className="min-w-0 flex-1 overflow-y-auto">{main}</main>
        ) : (
          <>
            {collapsed && <aside className="mail-list-rail" aria-label="已收起的邮件列表">
              <button type="button" aria-label="展开邮件列表" title="展开邮件列表" onClick={expand}>
                <PanelLeftOpen size={18} />
              </button>
              <span>邮件</span>
            </aside>}
            <section
              aria-label="列表"
              style={{ "--mail-list-width": `${layout.width}px` } as CSSProperties}
              className={cn(
                "mail-list-pane relative w-full min-h-0 shrink-0 flex-col border-r border-line bg-surface",
                collapsed && "mail-list-collapsed",
                showDetail ? "hidden" : "flex",
              )}
            >
              <div className="mail-list-controls">
                <span>邮件列表</span>
                <label title="打开邮件时自动收起列表，展开按钮始终保留">
                  <input type="checkbox" checked={layout.autoHide} onChange={event => {
                    setLayout(value => ({ ...value, autoHide: event.target.checked }));
                    setHidden(false); setExpandedFor(undefined);
                  }} />
                  阅读时隐藏
                </label>
                <button type="button" aria-label="收起邮件列表" title="收起邮件列表" disabled={!showDetail} onClick={() => setHidden(true)}>
                  <PanelLeftClose size={17} />
                </button>
              </div>
              {list}
              <PaneResize label="调整邮件列表宽度" value={layout.width} min={260} max={600}
                onChange={width => setLayout(value => ({ ...value, width }))}
                onReset={() => setLayout(value => ({ ...value, width: DEFAULT_WIDTH }))} />
            </section>
            <main className={cn("mail-reader-pane min-w-0 flex-1 flex-col md:flex", showDetail ? "flex" : "hidden")}>
              {customer && <div className="mail-customer-mobile-bar"><button type="button" onClick={() => setCustomerOpen(true)} aria-expanded={customerOpen}><CircleUserRound size={17} strokeWidth={1.75} />客户需求</button></div>}
              {detail}
            </main>
            {customer && <aside className="mail-customer-pane" data-open={customerOpen} aria-label="客户需求栏"><header><span><CircleUserRound size={17} strokeWidth={1.75} />客户工作区</span><button type="button" aria-label="返回邮件原文" onClick={() => setCustomerOpen(false)}><X size={17} strokeWidth={1.75} /></button></header><div className="mail-customer-scroll">{customer}</div></aside>}
            {assistant}
          </>
        )}
      </div>
    </div>
  );
}
