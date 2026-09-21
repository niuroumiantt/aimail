import { Inbox, Palette, RefreshCw, Users } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router";
import type { MailboxInfo } from "@/data/types";
import { cn } from "@/lib/cn";
import { FOLDER_LABEL, FOLDER_ORDER, type FolderKey } from "./folders";
import { ThemeToggle } from "./theme-toggle";

const NAV_ITEM =
  "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink current:bg-surface-3 current:font-medium current:text-ink";

/** 左栏:产品标、三个主入口、收件箱分组。分组的计数是真的,从数据来。
 *  aria-current 自己算:分组靠 ?f= 区分,路由库的匹配不看查询串。 */
export function Sidebar({
  counts,
  activeFolder,
  inInbox,
  mailbox,
  onSync,
  syncing = false,
}: {
  counts: Record<FolderKey, number>;
  activeFolder: FolderKey;
  inInbox: boolean;
  /** 伺候的邮箱;没开线索任务就不给线索入口 */
  mailbox: MailboxInfo;
  onSync?: () => Promise<string>;
  syncing?: boolean;
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
      className="flex h-full w-56 shrink-0 flex-col gap-6 border-r border-line bg-canvas px-3 py-4"
    >
      <div className="flex items-center gap-2.5 px-2">
        <span aria-hidden className="grid size-7 place-items-center rounded-md bg-brand text-on-brand">
          <Inbox size={15} strokeWidth={2.25} />
        </span>
        <div className="leading-tight">
          <h1 className="text-sm font-semibold tracking-tight text-ink">mail2leads</h1>
          <p className="truncate font-mono text-2xs text-ink-2" title={mailbox.address}>
            {mailbox.address || "…"}
          </p>
        </div>
      </div>

      <ul className="grid gap-0.5">
        <li>
          <Link to="/" className={NAV_ITEM} aria-current={current(inInbox)}>
            <Inbox size={16} strokeWidth={1.75} />
            收件箱
          </Link>
        </li>
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
            <Palette size={16} strokeWidth={1.75} />
            组件
          </Link>
        </li>
      </ul>

      {onSync && <div>
        <button
          type="button"
          onClick={() => void syncNow()}
          disabled={syncing}
          className="flex h-8 w-full items-center justify-center gap-2 rounded-md bg-surface-2 px-2.5 text-sm font-medium text-ink transition-colors hover:bg-surface-3 disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCw className={syncing ? "animate-spin" : ""} size={15} strokeWidth={2} />
          {syncing ? "正在收信…" : "立即收信"}
        </button>
        {syncError && <p className="mt-1 px-1 text-2xs text-danger">{syncError}</p>}
      </div>}

      <div className="grid gap-1">
        <h2 className="px-2.5 text-2xs font-medium uppercase tracking-wider text-ink-3">收件箱</h2>
        <ul className="grid gap-0.5">
          {FOLDER_ORDER.map((key) => (
            <li key={key}>
              <Link
                to={key === "all" ? "/" : `/?f=${key}`}
                aria-current={inInbox && activeFolder === key ? "true" : undefined}
                className={cn(NAV_ITEM, "justify-between")}
              >
                {FOLDER_LABEL[key]}
                <span className="font-mono text-2xs tabular-nums text-ink-3">{counts[key]}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-auto flex items-center justify-between px-1">
        <span className="font-mono text-2xs text-ink-3">Spark · fast</span>
        <ThemeToggle />
      </div>
    </nav>
  );
}
