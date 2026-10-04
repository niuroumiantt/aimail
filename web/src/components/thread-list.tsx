import type { Thread } from "@/data/types";
import { useNavigate } from "react-router";
import { EmptyState } from "./empty-state";
import { FOLDER_LABEL, FOLDER_ORDER, type FolderKey } from "./folders";
import { SearchBox } from "./search-box";
import { ThreadRow } from "./thread-row";
import { useState } from "react";
import { AlignLeft, ChevronDown, ChevronRight, List } from "lucide-react";

export function ThreadList({
  threads,
  folder,
  search,
  loading = false,
  error,
}: {
  threads: Thread[];
  folder: FolderKey;
  search: string;
  loading?: boolean;
  error?: string;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [preferences, setPreferences] = useState(() => {
    try { const stored = JSON.parse(localStorage.getItem("aimail-list-preferences") ?? "{}"); return { compact: stored.compact === true, grouped: stored.grouped === true }; }
    catch { return { compact: false, grouped: false }; }
  });
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const changePreferences = (patch: Partial<typeof preferences>) => {
    const next = { ...preferences, ...patch }; setPreferences(next);
    try { localStorage.setItem("aimail-list-preferences", JSON.stringify(next)); } catch { /* 当前列表仍可调整。 */ }
  };
  const term = query.trim().toLocaleLowerCase();
  const visible = threads.filter(thread => [thread.company, thread.contact, thread.email, thread.subject, thread.reading?.status === "ok" ? thread.reading.summary_zh : ""].join(" ").toLocaleLowerCase().includes(term));
  const groups = new Map<string, Thread[]>();
  for (const thread of visible) { const email = thread.email.trim().toLowerCase(); groups.set(email, [...(groups.get(email) ?? []), thread]); }
  return (
    <>
      <header className="mail-list-header">
        <div className="mail-list-title">
          <h2>{FOLDER_LABEL[folder]}</h2>
          <span>{threads.length}</span>
        </div>
        <select aria-label="邮件分组" value={folder} className="h-8 min-w-0 rounded-md border border-line bg-surface px-2 text-sm text-ink md:hidden"
          onChange={e => navigate(e.target.value === "all" ? "/" : `/?f=${e.target.value}`)}>
          {FOLDER_ORDER.map(key => <option key={key} value={key}>{FOLDER_LABEL[key]}</option>)}
        </select>
        <SearchBox value={query} onChange={setQuery} />
        <div className="mail-view-controls"><div><button type="button" aria-pressed={preferences.compact} onClick={() => changePreferences({ compact: true })}><List size={14} />简洁</button><button type="button" aria-pressed={!preferences.compact} onClick={() => changePreferences({ compact: false })}><AlignLeft size={14} />概括</button></div><label><input type="checkbox" checked={preferences.grouped} onChange={event => changePreferences({ grouped: event.target.checked })} />按联系人聚拢</label></div>
      </header>
      {error && <p role="alert" className="border-b border-line px-4 py-3 text-xs text-danger-text">加载失败：{error}。请刷新页面重试。</p>}
      <div aria-busy={loading} className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <p role="status" className="px-4 py-6 text-sm text-ink-2">正在加载邮件…</p>
        ) : visible.length === 0 && !error ? (
          <EmptyState title={term ? "没有匹配的邮件" : "这个分组是空的"} subtitle={term ? "试试联系人、公司名称或邮件主题。" : folder === "trash" ? "删除的会话会出现在这里，可以恢复。" : "邮件保留在全部列表，买卖相关往来会突出显示。"} />
        ) : (
          preferences.grouped ? [...groups.entries()].map(([email, items]) => <section key={email} className="mail-contact-group"><button className="mail-contact-heading" type="button" aria-expanded={!collapsed.includes(email)} onClick={() => setCollapsed(current => current.includes(email) ? current.filter(value => value !== email) : [...current, email])}>{collapsed.includes(email) ? <ChevronRight size={14} strokeWidth={1.75} /> : <ChevronDown size={14} strokeWidth={1.75} />}<span>{items[0].contact}<small>{email}</small></span><small>{items.length} 个话题</small></button>{!collapsed.includes(email) && items.map(thread => <ThreadRow key={thread.id} thread={thread} search={search} compact={preferences.compact} />)}</section>)
            : visible.map((t) => <ThreadRow key={t.id} thread={t} search={search} compact={preferences.compact} />)
        )}
      </div>
    </>
  );
}
