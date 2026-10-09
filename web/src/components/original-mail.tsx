import { useEffect, useMemo, useRef, useState } from "react";
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
    for (const name of ["--font-sans", "--ui-font-reading", "--color-mail-paper", "--color-mail-ink", "--color-mail-line", "--color-mail-wash"]) {
      doc.documentElement.style.setProperty(name, host.getPropertyValue(name));
    }
    // Reading typography uses the same light paper and colors in both application themes.
    doc.documentElement.style.setProperty("--mail-document-link", host.getPropertyValue("--color-brand"));
    let active = true;
    let pending = 0;
    const resize = () => {
      pending = 0;
      // Hidden comparison columns and detached documents have zero geometry. Never
      // let their late font/image callbacks overwrite the visible message height.
      if (!active || element.contentDocument !== doc || !element.getBoundingClientRect().width) return;
      const height = Math.max(80, Math.ceil(Math.max(doc.body.scrollHeight, doc.body.getBoundingClientRect().height)) + 2);
      if (element.style.getPropertyValue("--mail-document-height") !== `${height}px`) element.style.setProperty("--mail-document-height", `${height}px`);
    };
    const schedule = () => { if (active && !pending) pending = requestAnimationFrame(resize); };
    const observer = new ResizeObserver(schedule);
    observer.observe(doc.body);
    observer.observe(element);
    doc.addEventListener("load", schedule, true);
    doc.addEventListener("toggle", schedule, true);
    void doc.fonts?.ready.then(schedule);
    schedule();
    cleanup.current = () => { active = false; cancelAnimationFrame(pending); observer.disconnect(); doc.removeEventListener("load", schedule, true); doc.removeEventListener("toggle", schedule, true); };
  }

  return <div className="mail-original-html">
    <iframe ref={frame} className="mail-original-html-frame" title="客户原始邮件" srcDoc={document.srcDoc}
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
      onLoad={loaded} />
    {document.blockedImages && <p className="mail-original-notice">部分图片未加载。{document.externalImages && <button type="button" onClick={() => setLoadedSource(source)}>加载本封外部图片</button>} 缺失的内嵌图片保留占位。</p>}
  </div>;
}
