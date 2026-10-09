import { CircleUserRound, RefreshCw, Reply, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { Link } from "react-router";
import type { Thread } from "@/data/types";

export function InboxToolbar({ thread, syncing, onSync, replying, onReply, assistantOpen, onAssistant, busy, onOrganize }: {
  thread?: Thread; syncing: boolean; onSync: () => void;
  replying: boolean; onReply: () => void; assistantOpen: boolean; onAssistant: () => void;
  busy: boolean; onOrganize: () => void;
}) {
  return <div className="mail-command-actions" aria-label="邮件操作">
    <button type="button" disabled={!thread || Boolean(thread.deleted_at)} aria-pressed={replying} onClick={onReply}><Reply size={18} />回复</button>
    <button type="button" disabled={!thread || busy} onClick={onOrganize}>{thread?.deleted_at ? <RotateCcw size={18} /> : <Trash2 size={18} />}{busy ? "处理中…" : thread?.deleted_at ? "恢复" : "删除"}</button>
    <span className="mail-command-divider" />
    <button type="button" disabled={syncing} onClick={onSync}><RefreshCw size={18} className={syncing ? "animate-spin" : ""} />{syncing ? "同步中…" : "同步"}</button>
    <button type="button" disabled={!thread} aria-pressed={assistantOpen} onClick={onAssistant}><Sparkles size={18} />AI 阅读</button>
    {thread && !thread.deleted_at && import.meta.env.VITE_DATA_SOURCE === "api" && <Link to={`/followups/${thread.id}`}><CircleUserRound size={18} />分配</Link>}
  </div>;
}
