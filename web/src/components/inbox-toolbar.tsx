import { CircleUserRound, Reply, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { Link } from "react-router";
import type { Thread } from "@/data/types";

export function InboxToolbar({ thread, replying, onReply, assistantOpen, onAssistant, busy, onOrganize }: {
  thread?: Thread;
  replying: boolean; onReply: () => void; assistantOpen: boolean; onAssistant: () => void;
  busy: boolean; onOrganize: () => void;
}) {
  return <div className="mail-command-actions" role="toolbar" aria-label="当前邮件操作">
    <button type="button" disabled={!thread || Boolean(thread.deleted_at)} aria-pressed={replying} onClick={onReply}><Reply size={18} />回复</button>
    <button type="button" disabled={!thread || busy} onClick={onOrganize}>{thread?.deleted_at ? <RotateCcw size={18} /> : <Trash2 size={18} />}{busy ? "处理中…" : thread?.deleted_at ? "恢复" : "删除"}</button>
    <button type="button" disabled={!thread} aria-pressed={assistantOpen} onClick={onAssistant}><Sparkles size={18} />AI 阅读</button>
    {thread && !thread.deleted_at && import.meta.env.VITE_DATA_SOURCE === "api" && <Link to={`/followups/${thread.id}`}><CircleUserRound size={18} />分配</Link>}
  </div>;
}
