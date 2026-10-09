import { Dialog as RadixDialog } from "radix-ui";
import { ChevronDown, Download, FileText, Languages, LoaderCircle, Paperclip, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { AttachmentRef, AttachmentText, Message, MessageTranslation } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { Pill } from "./pill";
import { Tip } from "./tip";
import { AttachmentPreview } from "./attachment-preview";
import { OriginalMail } from "./original-mail";
import { PlainMail } from "./plain-mail";
import "@/tokens/message-translation.css";

type TranslationMode = "original" | "zh" | "compare";

export type TranslationHandlers = {
  onGetTranslation?: (messageId: string) => Promise<MessageTranslation | null>;
  onTranslate?: (messageId: string, force?: boolean) => Promise<MessageTranslation>;
};

function sizeLabel(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** 附件片:读出来的带文档图标可点开;读不出的带警告和原因——读不出要显形,不是装没看见。 */
function AttachmentChip({
  attachment,
  onOpen,
  original = false,
}: {
  attachment: AttachmentRef;
  original?: boolean;
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
  const label = original ? `${attachment.name} · ${sizeLabel(attachment.size)} · 查看原始附件` : failed
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
        disabled={!onOpen || !original && attachment.read === "none"}
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

/** Download exact stored bytes with the same mailbox scope as the preview. */
function AttachmentDownload({ attachment, load }: { attachment: AttachmentRef; load: (id: string) => Promise<Blob> }) {
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const active = useRef(true);
  const downloading = useRef(false);
  const urls = useRef(new Set<string>());
  useEffect(() => {
    active.current = true;
    const current = urls.current;
    return () => { active.current = false; current.forEach(url => URL.revokeObjectURL(url)); current.clear(); };
  }, []);
  const download = async () => {
    if (downloading.current) return;
    downloading.current = true; setPending(true); setFailed(false);
    try {
      const blob = await load(attachment.id);
      if (!active.current) return;
      const url = URL.createObjectURL(blob);
      urls.current.add(url);
      const link = document.createElement("a");
      link.href = url; link.download = attachment.name;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => { if (urls.current.delete(url)) URL.revokeObjectURL(url); }, 1000);
    } catch { if (active.current) setFailed(true); }
    finally { downloading.current = false; if (active.current) setPending(false); }
  };
  return <div className="mail-attachment-download">
    <button type="button" onClick={() => void download()} disabled={pending} aria-label={`下载 ${attachment.name}`}>
      {pending ? <LoaderCircle size={14} className="animate-spin" aria-hidden /> : <Download size={14} aria-hidden />}{pending ? "下载中…" : "下载原件"}
    </button>
    {failed && <small role="alert">下载失败，请重试</small>}
  </div>;
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
  onAttachmentFile,
  onGetTranslation,
  onTranslate,
  mailboxAddress,
}: TranslationHandlers & {
  message: Message;
  /** 取一份附件的文字;没有就只列名字 */
  onAttachment?: (attachmentId: string) => Promise<AttachmentText>;
  onAttachmentFile?: (attachmentId: string) => Promise<Blob>;
  mailboxAddress?: string;
}) {
  const [showQuoted, setShowQuoted] = useState(false);
  const [previewFile, setPreviewFile] = useState(true);
  const [opened, setOpened] = useState<AttachmentRef | null>(null);
  const [content, setContent] = useState<AttachmentText | { error: string } | null>(null);
  const [translated, setTranslated] = useState<{ source: string; value: MessageTranslation } | null>(null);
  const [display, setDisplay] = useState<{ source: string; mode: TranslationMode } | null>(null);
  const [translationError, setTranslationError] = useState<{ source: string; message: string } | null>(null);
  const [pendingTranslation, setPendingTranslation] = useState<{ source: string; phase: "cache" | "model" } | null>(null);
  const activeRequest = useRef(0);
  const source = `${message.id}\n${message.body}\n${message.body_html ?? ""}`;
  const translation = translated?.source === source ? translated.value : null;
  const mode = display?.source === source ? display.mode : "original";
  const translationPending = pendingTranslation?.source === source;
  const error = translationError?.source === source ? translationError.message : "";
  const out = message.direction === "out";
  const quotedLines = message.quoted ? message.quoted.split("\n").length : 0;

  useEffect(() => {
    if (!onGetTranslation) return;
    let cancelled = false;
    const requests = activeRequest;
    const generation = requests.current;
    void onGetTranslation(message.id).then(result => {
      if (!cancelled && generation === requests.current && result?.status === "ok") setTranslated({source, value: result});
    }).catch(() => {});
    return () => {cancelled = true; requests.current++;};
  }, [source, message.id, onGetTranslation]);

  const translate = async (force = false) => {
    if (!onTranslate || translationPending) return;
    const request = ++activeRequest.current;
    setTranslationError(null);
    setPendingTranslation({ source, phase: "cache" });
    try {
      let result = !force && onGetTranslation ? await onGetTranslation(message.id) : null;
      if (request !== activeRequest.current) return;
      if (result?.status !== "ok") {
        setPendingTranslation({ source, phase: "model" });
        result = force ? await onTranslate(message.id, true) : await onTranslate(message.id);
      }
      if (request !== activeRequest.current) return;
      if (result.status === "ok") {
        setTranslated({ source, value: result });
        setDisplay({ source, mode: "zh" });
      } else {
        setTranslationError({ source, message: result.reason || "翻译暂不可用，请重试。原文仍可阅读。" });
      }
    } catch (reason) {
      if (request === activeRequest.current) {
        const unavailable = reason instanceof Error && reason.message === "所选模型暂不可用，仍可阅读原文与已保存的译文。";
        setTranslationError({ source, message: unavailable ? "当前翻译模型未连接，请点击顶栏的模型图标检查连接状态。原文仍可阅读。" : "翻译暂不可用，请重试。原文仍可阅读。" });
      }
    } finally {
      if (request === activeRequest.current) setPendingTranslation(null);
    }
  };

  const open = onAttachment || onAttachmentFile
    ? async (a: AttachmentRef) => {
        setOpened(a);
        setPreviewFile(true);
        setContent(null);
        if (onAttachmentFile) return;
        try {
          setContent(await onAttachment!(a.id));
        } catch (e) {
          setContent({ error: e instanceof Error ? e.message : String(e) });
        }
      }
    : undefined;

  return (
    <article id={`mail-${message.id}`} className="mail-original-message grid gap-2">
      <header className="mail-message-header flex flex-wrap items-center gap-x-2 gap-y-1">
        <Avatar name={message.from_name} className="mail-contact-avatar mail-message-avatar" />
        <div className="mail-message-sender">
        <span className="text-sm font-medium text-ink">{message.from_name}</span>
        {out && <Pill tone="brand">我方</Pill>}
        <span className="truncate text-xs text-ink-2">{message.from_email}</span>
        {mailboxAddress && <small className="mail-message-recipient">当前邮箱：{mailboxAddress}</small>}
        </div>
        <time className="ml-auto text-xs tabular-nums text-ink-2" dateTime={message.sent_at}>
          {fullTime(message.sent_at)}
        </time>
        {onTranslate && message.body.trim() && (
          <div className="mail-translation-tools">
            {translation?.status === "ok" ? (
              <div className="mail-translation-modes" role="group" aria-label="正文显示方式">
                {([
                  ["original", "原文"],
                  ["zh", "中文"],
                  ["compare", "对照"],
                ] as const).map(([value, label]) => (
                  <button key={value} type="button" aria-pressed={mode === value}
                    onClick={() => setDisplay({ source, mode: value })}>{label}</button>
                ))}
              </div>
            ) : (
              <button type="button" className="mail-translation-button" disabled={translationPending}
                onClick={() => void translate()}>
                {translationPending ? <LoaderCircle size={14} strokeWidth={1.75} className="mail-translation-spinner" /> : <Languages size={14} strokeWidth={1.75} />}
                {translationPending ? pendingTranslation?.phase === "cache" ? "读取译文…" : "正在翻译…" : error ? "重试翻译" : "翻译"}
              </button>
            )}
          </div>
        )}
        {onTranslate && translation?.status === "ok" && <button type="button" className="mail-translation-button" disabled={translationPending} onClick={()=>void translate(true)}><Languages size={14}/>{translationPending ? "正在翻译…" : "重新翻译"}</button>}
      </header>

      <div
        className={cn(
          "mail-message-content rounded-lg border px-4 py-3 text-sm leading-relaxed text-ink",
          out ? "border-brand-line/60 bg-brand-wash/50" : "border-line bg-surface",
        )}
      >
        <div className="mail-message-texts" data-mode={translation ? mode : "original"}>
          <section className="mail-message-text" aria-label="邮件原文" hidden={translation !== null && mode === "zh"}>
            {translation && mode === "compare" && <h3>原文</h3>}
            {message.body_html ? <OriginalMail message={message} /> : <PlainMail text={message.body} />}
            {message.original_notice && <p className="mail-original-notice">{message.original_notice}</p>}
          </section>
          {translation?.status === "ok" && <section className="mail-message-text mail-message-translated" aria-label="中文译文" hidden={mode === "original"}>
            {mode === "compare" && <h3>中文译文</h3>}
            {translation.html_zh ? <OriginalMail translated message={{...message, body_html: translation.html_zh}} /> : <PlainMail text={translation.text_zh} />}
            {translation.layout_notice && <p className="mail-translation-note">{translation.layout_notice}</p>}
          </section>}
        </div>
        {translationPending && <p role="status" className="mail-translation-note">翻译期间可继续阅读原文。</p>}
        {error && <p role="alert" className="mail-translation-error">{error}</p>}
        {translation?.status === "ok" && mode !== "original" && (
          <footer className="mail-translation-note">
            <span>
              中文翻译 · {translation.model} · {translation.task_version}
            </span>
            <time dateTime={translation.produced_at}>{fullTime(translation.produced_at)}</time>
            <span>邮件 #{message.id}</span>
            <span>仅翻译本封正文；引用历史与附件保留原文。请以原文核对交易信息。</span>
          </footer>
        )}
        {message.attachments && message.attachments.length > 0 && (
          <section className="mail-attachments" aria-label="邮件附件">
            <h3><Paperclip size={14} aria-hidden />附件 <span>{message.attachments.length}</span></h3>
            {message.attachments.map((a) => (
              <div className="mail-attachment-item" key={a.id}>
                <AttachmentChip attachment={a} original={Boolean(onAttachmentFile)} onOpen={open} />
                <small>{sizeLabel(a.size)}</small>
                {onAttachmentFile && <AttachmentDownload attachment={a} load={onAttachmentFile} />}
              </div>
            ))}
          </section>
        )}
        {message.quoted && !message.body_html && (
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

      {onAttachmentFile && previewFile ? <AttachmentPreview key={opened?.id} attachment={opened} load={onAttachmentFile}
        onClose={() => setOpened(null)} onText={onAttachment && opened ? async () => {
          setPreviewFile(false); setContent(null);
          try { setContent(await onAttachment(opened.id)); }
          catch { setContent({ error: "附件文字暂不可用，请重试。" }); }
        } : undefined} /> : <AttachmentSheet attachment={opened} content={content} onClose={() => setOpened(null)} />}
    </article>
  );
}
