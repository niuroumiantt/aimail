import { SESSION_EXPIRED_MESSAGE } from "@/lib/session-auth";
import type { Thread, GroupTrashRequest } from "@/data/types";
import { useListCaptions, type LoadCaptions } from "@/data/list-captions";
import { ConfirmDialog } from "./dialog";
import { useNavigate } from "react-router";
import { EmptyState } from "./empty-state";
import { FOLDER_LABEL, FOLDER_ORDER, type FolderKey } from "./folders";
import { SearchBox } from "./search-box";
import { ThreadRow } from "./thread-row";
import { useState, type ReactNode } from "react";
import { AlignLeft, ChevronDown, ChevronRight, List, Trash2 } from "lucide-react";

export function ThreadList({
  threads,
  folder,
  search,
  loading = false,
  error,
  query: controlledQuery,
  headerControl,
  notice,
  title,
  dragScope,
  onTrashGroup,
  loadCaptions,
}: {
  threads: Thread[];
  folder: FolderKey;
  search: string;
  loading?: boolean;
  error?: string;
  query?: string;
  headerControl?: ReactNode;
  notice?: string;
  title?: string;
  dragScope?: string;
  onTrashGroup?: (request: GroupTrashRequest) => Promise<string>;
  loadCaptions?: LoadCaptions;
}) {
  const navigate = useNavigate();
  const [localQuery, setQuery] = useState("");
  const query = controlledQuery ?? localQuery;
  const [preferences, setPreferences] = useState(() => {
    try { const stored = JSON.parse(localStorage.getItem("aimail-list-preferences") ?? "{}"); return { compact: stored.compact === true, grouped: stored.grouped === true }; }
    catch { return { compact: false, grouped: false }; }
  });
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [deleting, setDeleting] = useState<{ email: string; name: string; request: GroupTrashRequest }>();
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const changePreferences = (patch: Partial<typeof preferences>) => {
    const next = { ...preferences, ...patch }; setPreferences(next);
    try { localStorage.setItem("aimail-list-preferences", JSON.stringify(next)); } catch { /* 当前列表仍可调整。 */ }
  };
  const term = query.trim().toLocaleLowerCase();
  const visible = threads.filter(thread => [thread.company, thread.contact, thread.email, thread.subject, thread.reading?.status === "ok" ? thread.reading.summary_zh : ""].join(" ").toLocaleLowerCase().includes(term))
    .sort((a, b) => (Date.parse(b.updated_at) || 0) - (Date.parse(a.updated_at) || 0));
  const captions = useListCaptions(visible, preferences.compact && !loading, loadCaptions);
  const row = (thread: Thread) => <ThreadRow key={thread.id} thread={{ ...thread, caption: captions.values[thread.id] ?? thread.caption }} search={search} compact={preferences.compact} dragScope={dragScope} />;
  const remove = async () => {
    if (!deleting || !onTrashGroup || busy) return;
    setBusy(true); setDeleteError("");
    try {
      const error = await onTrashGroup(deleting.request);
      if (error) setDeleteError(error); else setDeleting(undefined);
    } catch (e) { setDeleteError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const groups = new Map<string, Thread[]>();
  for (const thread of visible) { const email = thread.email.trim().toLowerCase(); groups.set(email, [...(groups.get(email) ?? []), thread]); }
  const dates = new Map<string, Thread[]>();
  for (const thread of visible) {
    const label = dateGroup(thread.updated_at);
    dates.set(label, [...(dates.get(label) ?? []), thread]);
  }
  return (
    <>
      <header className="mail-list-header">
        <div className="mail-list-title">
          <h2 title={title}>{title ?? FOLDER_LABEL[folder]}</h2>
          <span>{threads.length}</span>
          {headerControl}
        </div>
        <select aria-label="邮件分组" value={title ? "custom" : folder} className="h-8 min-w-0 rounded-md border border-line bg-surface px-2 text-sm text-ink md:hidden"
          onChange={e => navigate(e.target.value === "all" ? "/" : `/?f=${e.target.value}`)}>
          {title && <option value="custom">{title}</option>}
          {FOLDER_ORDER.map(key => <option key={key} value={key}>{FOLDER_LABEL[key]}</option>)}
        </select>
        {controlledQuery === undefined && <SearchBox value={query} onChange={setQuery} />}
        <div className="mail-view-controls"><div><button type="button" aria-pressed={preferences.compact} onClick={() => changePreferences({ compact: true })}><List size={14} />简洁</button><button type="button" aria-pressed={!preferences.compact} onClick={() => changePreferences({ compact: false })}><AlignLeft size={14} />概括</button></div><label><input type="checkbox" checked={preferences.grouped} onChange={event => changePreferences({ grouped: event.target.checked })} />按联系人聚拢</label></div>
      </header>
      {notice && <p role="status" className="mail-sync-notice">{notice}</p>}
      {preferences.compact && (captions.error || captions.failed) && <p role="status" className="mail-caption-notice">{captions.error || "部分中文描述暂不可用"} <button type="button" onClick={captions.retry}>重试中文描述</button></p>}
      {error && <p role="alert" className="border-b border-line px-4 py-3 text-xs text-danger-text">{error === SESSION_EXPIRED_MESSAGE ? "登录已过期，重新登录后会恢复邮件列表。" : `加载失败：${error}。请刷新页面重试。`}</p>}
      <div aria-busy={loading} className="mail-thread-list-scroll min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <p role="status" className="px-4 py-6 text-sm text-ink-2">正在加载邮件…</p>
        ) : visible.length === 0 && !error ? (
          <EmptyState title={term ? "没有匹配的邮件" : "这个分组是空的"} subtitle={term ? "试试联系人、公司名称或邮件主题。" : folder === "trash" ? "删除的会话会出现在这里，可以恢复。" : "邮件保留在全部列表，买卖相关往来会突出显示。"} />
        ) : (
          preferences.grouped ? [...groups.entries()].map(([email, items]) => <section key={email} className="mail-contact-group"><div className="mail-contact-group-header"><button className="mail-contact-heading" type="button" aria-expanded={!collapsed.includes(email)} onClick={() => setCollapsed(current => current.includes(email) ? current.filter(value => value !== email) : [...current, email])}>{collapsed.includes(email) ? <ChevronRight size={14} strokeWidth={1.75} /> : <ChevronDown size={14} strokeWidth={1.75} />}<span>{items[0].contact}<small>{email}</small></span><small>{items.length} 个话题</small></button>{onTrashGroup && folder !== "trash" && <button type="button" className="mail-group-trash" aria-label={`整组删除 ${items[0].contact || email}`} title="删除当前列表中此联系人的全部话题" onClick={() => {
            setDeleteError(""); setDeleting({ email, name: items[0].contact || email, request: { email, threads: items.map(t => ({ id: t.id, updated_at: t.updated_at, message_count: t.message_count ?? t.messages.length })) } });
          }}><Trash2 size={14} aria-hidden /><span>整组删除</span></button>}</div>{!collapsed.includes(email) && items.map(row)}</section>)
            : ["今天", "昨天", "本周", "更早", "日期未知"].filter(label => dates.has(label)).map(label => <section key={label} aria-label={label}>
              <div className="mail-date-heading"><ChevronDown size={14} aria-hidden />{label}</div>
              {dates.get(label)!.map(row)}
            </section>)
        )}
      </div>
      <ConfirmDialog destructive open={Boolean(deleting)} onOpenChange={open => { if (!open) setDeleting(undefined); }} busy={busy}
        title="⚠️ 确认整组删除？"
        description={deleting ? `将删除当前列表中 ${deleting.name}（${deleting.email}）的 ${deleting.request.threads.length} 个话题，共 ${deleting.request.threads.reduce((sum, t) => sum + t.message_count, 0)} 封邮件。包含这些话题中的来信和回复。` : ""}
        confirmLabel={busy ? "正在删除…" : "确认移入回收站"} onConfirm={() => void remove()}>
        <p className="text-sm text-ink-2">仅影响当前视图和搜索结果中的这一组。可在回收站恢复，原始邮件和附件备份保留。</p>
        {deleteError && <p role="alert" className="text-sm text-danger-text">{deleteError}</p>}
      </ConfirmDialog>
    </>
  );
}

/** Local calendar boundaries, rather than elapsed 24-hour intervals. */
export function dateGroup(value: string, now = new Date()): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || date > now) return "日期未知";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const week = new Date(today); week.setDate(today.getDate() - (today.getDay() + 6) % 7);
  return date >= today ? "今天" : date >= yesterday ? "昨天" : date >= week ? "本周" : "更早";
}
