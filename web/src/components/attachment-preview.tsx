import { Dialog } from "radix-ui";
import { Download, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { AttachmentRef } from "@/data/types";
import "@/tokens/attachment-preview.css";

/** View the immutable file; extracted text is a separate, optional view. */
export function AttachmentPreview({ attachment, load, onClose, onText }: {
  attachment: AttachmentRef | null;
  load: (id: string) => Promise<Blob>;
  onClose: () => void;
  onText?: () => void;
}) {
  const [file, setFile] = useState<{ url: string; pdf: boolean }>();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!attachment) return;
    let alive = true;
    let url: string | undefined;
    void load(attachment.id).then(blob => {
      if (!alive) return;
      url = URL.createObjectURL(blob);
      setFile({ url, pdf: blob.type === "application/pdf" });
      setFailed(false);
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [attachment, load, attempt]);
  return <Dialog.Root open={attachment !== null} onOpenChange={open => !open && onClose()}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay" />
      <Dialog.Content className="mail-attachment-preview">
        <header>
          <FileText size={18} aria-hidden />
          <div><Dialog.Title>{attachment?.name}</Dialog.Title><Dialog.Description>原始附件</Dialog.Description></div>
          {file && <a href={file.url} download={attachment?.name}><Download size={16} aria-hidden />下载原件</a>}
          <Dialog.Close className="mail-icon-button" aria-label="关闭附件预览"><X size={18} /></Dialog.Close>
        </header>
        <div className="mail-attachment-preview-body">
          {!file && !failed && <p role="status">正在加载原始附件…</p>}
          {!file && failed && <div><p role="alert">原始附件暂时无法加载，请重试。</p><button type="button" onClick={() => { setFailed(false); setAttempt(value => value + 1); }}>重新加载</button></div>}
          {file?.pdf && <iframe title="PDF 原件预览" src={`${file.url}#view=FitH`} />}
          {file && !file.pdf && <p>此类型暂不支持在线预览，请下载原件查看。</p>}
        </div>
        <footer><span>PDF 可在上方直接阅读；若浏览器未显示，请下载原件。</span>{onText && <button type="button" onClick={onText}>查看提取文字</button>}</footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
