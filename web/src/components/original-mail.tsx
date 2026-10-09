import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { mailDocument } from "@/lib/mail-document";
import type { Message } from "@/data/types";

export function OriginalMail({ message }: { message: Message }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const cleanup = useRef<(() => void) | null>(null);
  const [loadedSource, setLoadedSource] = useState<string | null>(null);
  const source = `${message.id}\n${message.body_html}`;
  const loadExternalImages = loadedSource === source;
  const document = useMemo(() => mailDocument(message.body_html ?? "", message.inline_images, loadExternalImages), [message.body_html, message.inline_images, loadExternalImages]);
  useEffect(() => () => cleanup.current?.(), []);

  function loaded() {
    cleanup.current?.();
    const element = frame.current;
    const doc = element?.contentDocument;
    if (!element || !doc) return;
    const host = getComputedStyle(element);
    for (const name of ["--font-sans", "--ui-font-reading", "--color-mail-paper", "--color-mail-ink"]) {
      doc.documentElement.style.setProperty(name, host.getPropertyValue(name));
    }
    // Keep sender-authored colors on a white document in both application themes.
    doc.documentElement.style.setProperty("--mail-document-link", host.getPropertyValue("--color-brand"));
    const resize = () => {
      const height = Math.min(30000, Math.max(80, doc.body.scrollHeight, doc.body.getBoundingClientRect().height));
      element.style.setProperty("--mail-document-height", `${height}px`);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(doc.body);
    doc.addEventListener("load", resize, true);
    void doc.fonts?.ready.then(resize);
    resize();
    cleanup.current = () => { observer.disconnect(); doc.removeEventListener("load", resize, true); };
  }

  return <div className="mail-original-html">
    <iframe ref={frame} className="mail-original-html-frame" title="客户原始邮件" srcDoc={document.srcDoc}
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
      style={{ "--mail-document-height": "80px" } as CSSProperties} onLoad={loaded} />
    {document.blockedImages && <p className="mail-original-notice">部分图片未加载。{document.externalImages && <button type="button" onClick={() => setLoadedSource(source)}>加载本封外部图片</button>} 缺失的内嵌图片保留占位。</p>}
  </div>;
}
