import { NavLink } from "react-router";
import type { Thread } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime, relativeTime } from "@/lib/text";
import { isLeadThread, MailLabel } from "./mail-label";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { Pill } from "./pill";
import { Zap } from "lucide-react";
import { Avatar } from "./avatar";

export function ThreadRow({ thread, search, compact = false }: { thread: Thread; search: string; compact?: boolean }) {
  const lead = isLeadThread(thread);
  const reading = thread.reading;
  const attributed = Boolean(reading?.model && reading.task_version && reading.produced_at);
  const suspect = reading?.status === "ok" && reading.unverified.length > 0;
  const preview = reading?.status === "failed" ? "识别失败，请阅读原文"
    : suspect ? "摘要中的数字未通过核对，请阅读原文。"
    : reading?.status === "ok" && attributed ? reading.summary_zh : "尚未识别";
  return (
    <NavLink
      to={{ pathname: `/t/${thread.id}`, search }}
      className={({ isActive }) =>
        cn(
          "mail-thread-row",
          compact && "mail-thread-compact",
          isActive && "mail-thread-selected",
          lead && "mail-thread-trade",
        )
      }
    >
      {compact && lead && <Zap className="mail-compact-trade" size={15} aria-label="SALES LEAD" />}
      {!compact && <Avatar name={thread.contact || thread.email} className="mail-contact-avatar mail-thread-avatar" />}
      {!compact && <div className="mail-thread-sender">
        <span title={thread.email}>{thread.contact || thread.email}</span>
        <MailLabel thread={thread} />
        {["quote", "replied"].includes(thread.folder) && <Pill className="mail-thread-progress" tone={FOLDER_TONE[thread.folder]}>{FOLDER_LABEL[thread.folder]}</Pill>}
      </div>}
      {!compact && <time className="mail-thread-time" dateTime={thread.updated_at}>
        {relativeTime(thread.updated_at)}
      </time>}
      <p className="mail-thread-subject" title={thread.subject}>{thread.subject}</p>
      {!compact && <p className="mail-thread-summary" data-warning={suspect || reading?.status === "failed" || undefined}
        title={attributed ? `${reading!.model} · ${reading!.task_version} · ${fullTime(reading!.produced_at)}` : undefined}>{preview}</p>}
    </NavLink>
  );
}
