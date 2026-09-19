import { ChevronDown, Paperclip } from "lucide-react";
import { useState } from "react";
import type { Message } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { Pill } from "./pill";

/** 一封信。引用历史默认折叠——业务员要看的是本封新增的那几行。 */
export function MessageView({ message }: { message: Message }) {
  const [showQuoted, setShowQuoted] = useState(false);
  const out = message.direction === "out";
  const quotedLines = message.quoted ? message.quoted.split("\n").length : 0;

  return (
    <article className="grid gap-2">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Avatar name={message.from_name} size="sm" muted={out} />
        <span className="text-sm font-medium text-ink">{message.from_name}</span>
        {out && <Pill tone="brand">我方</Pill>}
        <span className="truncate text-xs text-ink-2">{message.from_email}</span>
        <time className="ml-auto text-xs tabular-nums text-ink-2" dateTime={message.sent_at}>
          {fullTime(message.sent_at)}
        </time>
      </header>

      <div
        className={cn(
          "whitespace-pre-wrap rounded-lg border px-4 py-3 text-sm leading-relaxed text-ink",
          out ? "border-brand-line/60 bg-brand-wash/50" : "border-line bg-surface",
        )}
      >
        {message.body}
        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
            {message.attachments.map((name) => (
              <span
                key={name}
                className="inline-flex items-center gap-1 rounded-sm bg-surface-3 px-1.5 py-0.5 font-mono text-2xs text-ink-2"
              >
                <Paperclip size={11} strokeWidth={2} />
                {name}
              </span>
            ))}
          </div>
        )}
        {message.quoted && (
          <div className="mt-3 border-t border-line pt-2">
            <button
              type="button"
              aria-expanded={showQuoted}
              onClick={() => setShowQuoted((v) => !v)}
              className="inline-flex items-center gap-1 text-xs text-ink-2 hover:text-ink"
            >
              <ChevronDown
                size={13}
                strokeWidth={2}
                className={cn("transition-transform", showQuoted && "rotate-180")}
              />
              {showQuoted ? "收起引用历史" : "展开引用历史"}
              <span className="font-mono tabular-nums">{quotedLines} 行</span>
            </button>
            {showQuoted && (
              <pre className="mt-2 whitespace-pre-wrap border-l-2 border-line-2 pl-3 font-sans text-xs leading-relaxed text-ink-2">
                {message.quoted}
              </pre>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
