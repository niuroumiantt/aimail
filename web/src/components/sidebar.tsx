import { Archive, CheckCheck, Clock3, FileText, Inbox, ListTodo, Mail, Palette, RefreshCw, Tag, Trash2, Users, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import type { MailboxInfo } from "@/data/types";
import { cn } from "@/lib/cn";
import { FOLDER_LABEL, FOLDER_ORDER, type FolderKey } from "./folders";
import { ThemeToggle } from "./theme-toggle";

const NAV_ITEM = "mail-sidebar-link";
const FOLDER_ICON = { all: Mail, inbox: Clock3, quote: Tag, replied: CheckCheck, invalid: Archive, leads: Zap, trash: Trash2 };

/** 左栏:产品标、三个主入口、收件箱分组。分组的计数是真的,从数据来。
 *  aria-current 自己算:分组靠 ?f= 区分,路由库的匹配不看查询串。 */
export function Sidebar({
  counts,
  activeFolder,
  inInbox,
  mailbox,
  mailboxes = [],
  onMailboxChange,
  onSync,
  syncing = false,
  foldersOnly = false,
  personalFolders,
  customFolderActive = false,
}: {
  counts: Record<FolderKey, number>;
  activeFolder: FolderKey;
  inInbox: boolean;
  /** 伺候的邮箱;没开线索任务就不给线索入口 */
  mailbox: MailboxInfo;
  mailboxes?: MailboxInfo[];
  onMailboxChange?: (address: string) => Promise<void>;
  onSync?: () => Promise<string>;
  syncing?: boolean;
  foldersOnly?: boolean;
  personalFolders?: ReactNode;
  customFolderActive?: boolean;
}) {
  const { pathname } = useLocation();
  const [syncError, setSyncError] = useState("");
  const current = (on: boolean) => (on ? ("page" as const) : undefined);
  const syncNow = async () => {
    if (onSync) setSyncError(await onSync());
  };
  return (
    <nav
      aria-label="主导航"
      className={cn("mail-sidebar flex h-full w-full shrink-0 flex-col border-r border-line bg-surface-2", foldersOnly && "mail-folder-sidebar")}
    >
      <div className="mail-sidebar-mailbox">
        <div><span aria-hidden><Inbox size={16} /></span><strong>我的邮箱</strong></div>
        {(!foldersOnly || mailboxes.length <= 1) && <p title={mailbox.address}>{mailbox.address || "正在读取邮箱…"}</p>}
        {mailboxes.length > 1 && <select aria-label="查看邮箱" value={mailbox.address}
          onChange={e => void onMailboxChange?.(e.target.value)}
          className="border border-line bg-surface px-2 text-xs text-ink">
          {mailboxes.map(item => <option key={item.address} value={item.address}>{item.address}</option>)}
        </select>}
      </div>

      <ul className="mail-sidebar-nav">
        <li>
          <Link to="/" className={NAV_ITEM} aria-current={current(inInbox)}>
            <Inbox size={16} strokeWidth={1.75} />
            收件箱
          </Link>
        </li>
        <li><Link to="/followups" className={NAV_ITEM} aria-current={current(pathname.startsWith("/followups"))}><ListTodo size={17} />我的跟进</Link></li>
        {mailbox.tasks.includes("leads") && (
          <li>
            <Link to="/leads" className={NAV_ITEM} aria-current={current(pathname === "/leads")}>
              <Users size={16} strokeWidth={1.75} />
              线索
            </Link>
          </li>
        )}
        <li>
          <Link to="/kit" className={NAV_ITEM} aria-current={current(pathname === "/kit")}>
            <Palette size={17} />
            组件
          </Link>
        </li>
      </ul>

      {onSync && <div>
        <button
          type="button"
          onClick={() => void syncNow()}
          disabled={syncing}
          className="mail-sidebar-sync"
        >
          <RefreshCw className={syncing ? "animate-spin" : ""} size={16} />
          {syncing ? "正在收信…" : "立即收信"}
        </button>
        {syncError && <p className="mt-1 px-1 text-2xs text-danger">{syncError}</p>}
      </div>}

      <div className="mail-sidebar-section">
        <h2>邮件视图</h2>
        <ul className="mail-sidebar-nav">
          {FOLDER_ORDER.map((key) => {
            const Icon = FOLDER_ICON[key] ?? FileText;
            return (
            <li key={key}>
              <Link
                to={key === "all" ? "/" : `/?f=${key}`}
                aria-current={inInbox && !customFolderActive && activeFolder === key ? "true" : undefined}
                className={cn(NAV_ITEM)}
              >
                <Icon size={17} />
                <span>{FOLDER_LABEL[key]}</span>
                <span className="mail-sidebar-count">{counts[key]}</span>
              </Link>
            </li>
          ); })}
        </ul>
      </div>

      {personalFolders}
      <div className="mail-sidebar-footer">
        <span>原文保留 · AI 待核对</span>
        {!foldersOnly && <ThemeToggle />}
      </div>
    </nav>
  );
}
