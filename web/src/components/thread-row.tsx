import { NavLink } from "react-router";
import type { Thread } from "@/data/types";
import { cn } from "@/lib/cn";
import { relativeTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { Pill } from "./pill";
import { StatusGlyph } from "./status-glyph";

export function ThreadRow({ thread, search }: { thread: Thread; search: string }) {
  const lost = thread.folder === "invalid";
  return (
    <NavLink
      to={{ pathname: `/t/${thread.id}`, search }}
      className={({ isActive }) =>
        cn(
          "grid grid-cols-row gap-x-3 border-b border-line px-4 py-3 transition-colors",
          "hover:bg-surface-2",
          isActive && "bg-brand-wash/60 hover:bg-brand-wash/60",
          lost && "opacity-70",
        )
      }
    >
      <Avatar name={thread.contact} muted={lost} className="row-span-3 mt-0.5" />
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-semibold text-ink">{thread.company}</span>
        <Pill tone={FOLDER_TONE[thread.folder]}>{FOLDER_LABEL[thread.folder]}</Pill>
      </div>
      <time className="text-2xs tabular-nums text-ink-2" dateTime={thread.updated_at}>
        {relativeTime(thread.updated_at)}
      </time>
      <p className="col-span-2 truncate text-sm text-ink-2">{thread.subject}</p>
      <div className="flex min-w-0 items-center gap-1.5 text-2xs text-ink-2">
        <span className="truncate">{thread.region}</span>
        <span className="text-ink-3">·</span>
        <span className="truncate font-mono">{thread.scale}</span>
      </div>
      <span className="justify-self-end">
        <StatusGlyph reading={thread.reading} />
      </span>
    </NavLink>
  );
}
