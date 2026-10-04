import { NavLink } from "react-router";
import type { Thread } from "@/data/types";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { isLeadThread, MailLabel } from "./mail-label";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { Pill } from "./pill";
import { StatusGlyph } from "./status-glyph";

export function ThreadRow({ thread, search, compact = false }: { thread: Thread; search: string; compact?: boolean }) {
  const lead = isLeadThread(thread);
  return (
    <NavLink
      to={{ pathname: `/t/${thread.id}`, search }}
      className={({ isActive }) =>
        cn(
          "grid grid-cols-row gap-x-3 border-b border-line px-4 py-3 transition-colors",
          "mail-thread-row",
          compact && "mail-thread-compact",
          "hover:bg-surface-2",
          isActive && "bg-brand-wash/60 hover:bg-brand-wash/60",
          lead && "border-l-2 border-l-brand",
        )
      }
    >
      {!compact && <Avatar name={thread.contact} muted className="row-span-3 mt-0.5" />}
      <div className="mail-thread-sender flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-semibold text-ink">{thread.company}</span>
        <MailLabel thread={thread} />
        {["quote", "replied"].includes(thread.folder) && <Pill tone={FOLDER_TONE[thread.folder]}>{FOLDER_LABEL[thread.folder]}</Pill>}
      </div>
      <time className="mail-thread-time text-2xs tabular-nums text-ink-2" dateTime={thread.updated_at}>
        {relativeTime(thread.updated_at)}
      </time>
      <p className="mail-thread-subject col-span-2 truncate text-sm text-ink-2">{thread.subject}</p>
      {!compact && <p className="mail-thread-summary">{thread.reading?.status === "ok" ? thread.reading.summary_zh : thread.reading?.status === "failed" ? "识别失败，请阅读原文" : "尚未识别"}</p>}
      <div className="mail-thread-meta flex min-w-0 items-center gap-1.5 text-2xs text-ink-2">
        {thread.region && <span className="truncate">{thread.region}</span>}
        {thread.region && thread.scale && <span className="text-ink-3">·</span>}
        {thread.scale && <span className="truncate font-mono">{thread.scale}</span>}
      </div>
      <span className="justify-self-end">
        <StatusGlyph reading={thread.reading} />
      </span>
    </NavLink>
  );
}
