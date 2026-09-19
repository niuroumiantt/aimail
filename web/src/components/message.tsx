import { Dialog as RadixDialog } from "radix-ui";
import { ChevronDown, FileText, Paperclip, TriangleAlert, X } from "lucide-react";
import { useState } from "react";
import type { AttachmentRef, AttachmentText, Message } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { Pill } from "./pill";
import { Tip } from "./tip";

function sizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** 附件片:读出来的带文档图标可点开;读不出的带警告和原因——读不出要显形,不是装没看见。 */
function AttachmentChip({
  attachment,
  onOpen,
}: {
  attachment: AttachmentRef;
  onOpen?: (a: AttachmentRef) => void;
}) {
  const failed = attachment.read === "failed";
  const icon = failed ? (
    <TriangleAlert size={11} strokeWidth={2} />
  ) : attachment.read === "ok" ? (
    <FileText size={11} strokeWidth={2} />
  ) : (
    <Paperclip size={11} strokeWidth={2} />
  );
  const label = failed
    ? `${attachment.name}:没读出来,${attachment.reason ?? ""}`
    : attachment.read === "ok"
      ? `${attachment.name} · ${sizeLabel(attachment.size)} · 点开看读出的文字`
      : `${attachment.name} · ${sizeLabel(attachment.size)} · 还没读`;
  return (
    <Tip label={label}>
      <button
        type="button"
        data-testid="attachment"
        data-read={attachment.read}
        aria-label={label}
        disabled={!onOpen || attachment.read === "none"}
        onClick={() => onOpen?.(attachment)}
        className={cn(
          "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-mono text-2xs",
          failed ? "bg-warn-wash text-warn-text" : "bg-surface-3 text-ink-2 hover:bg-brand-wash hover:text-brand-text",
          "disabled:pointer-events-none",
        )}
      >
        {icon}
        {attachment.name}
      </button>
    </Tip>
  );
}

/** 附件文字的抽屉。读出来的原样显示(等宽,保留换行);读不出的说原因。 */
function AttachmentSheet({
  attachment,
  content,
  onClose,
}: {
  attachment: AttachmentRef | null;
  content: AttachmentText | { error: string } | null;
  onClose: () => void;
}) {
  return (
    <RadixDialog.Root open={attachment !== null} onOpenChange={(open) => !open && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-overlay" />
        <RadixDialog.Content className="fixed left-1/2 top-1/2 z-50 grid max-h-sheet w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 grid-rows-sheet rounded-xl border border-line bg-surface shadow-lg">
          <header className="flex items-center gap-2 border-b border-line px-5 py-3">
            <FileText size={15} strokeWidth={2} className="text-ink-2" />
            <RadixDialog.Title className="truncate font-mono text-sm text-ink">{attachment?.name}</RadixDialog.Title>
            <RadixDialog.Description className="text-xs text-ink-3">
              {attachment ? sizeLabel(attachment.size) : ""}
            </RadixDialog.Description>
            <RadixDialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="关闭" className="ml-auto" icon={<X size={15} strokeWidth={2} />} />
            </RadixDialog.Close>
          </header>
          <div className="overflow-y-auto px-5 py-4">
            {content === null && <p className="text-sm text-ink-2">读取中…</p>}
            {content !== null && "error" in content && (
              <p role="alert" className="text-sm text-danger-text">
                {content.error}
              </p>
            )}
            {content !== null && !("error" in content) && content.status === "ok" && (
              <pre data-testid="attachment-text" className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink">
                {content.text}
              </pre>
            )}
            {content !== null && !("error" in content) && content.status !== "ok" && (
              <p role="alert" className="rounded-md border border-warn-line bg-warn-wash px-3 py-2 text-sm text-warn-text">
                没读出来:{content.reason || "还没读"}
              </p>
            )}
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

/** 一封信。引用历史默认折叠——业务员要看的是本封新增的那几行。 */
export function MessageView({
  message,
  onAttachment,
}: {
  message: Message;
  /** 取一份附件的文字;没有就只列名字 */
  onAttachment?: (attachmentId: string) => Promise<AttachmentText>;
}) {
  const [showQuoted, setShowQuoted] = useState(false);
  const [opened, setOpened] = useState<AttachmentRef | null>(null);
  const [content, setContent] = useState<AttachmentText | { error: string } | null>(null);
  const out = message.direction === "out";
  const quotedLines = message.quoted ? message.quoted.split("\n").length : 0;

  const open = onAttachment
    ? async (a: AttachmentRef) => {
        setOpened(a);
        setContent(null);
        try {
          setContent(await onAttachment(a.id));
        } catch (e) {
          setContent({ error: e instanceof Error ? e.message : String(e) });
        }
      }
    : undefined;

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
            {message.attachments.map((a) => (
              <AttachmentChip key={a.id} attachment={a} onOpen={open} />
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

      <AttachmentSheet attachment={opened} content={content} onClose={() => setOpened(null)} />
    </article>
  );
}
