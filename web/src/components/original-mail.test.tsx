import { fireEvent, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { OriginalMail } from "./original-mail";

it("ignores late callbacks from replaced or hidden mail and remeasures the visible frame", async () => {
  const previousObserver = globalThis.ResizeObserver;
  const previousRaf = globalThis.requestAnimationFrame;
  const previousCancel = globalThis.cancelAnimationFrame;
  const callbacks: FrameRequestCallback[] = [];
  const observers: (() => void)[] = [];
  globalThis.requestAnimationFrame = callback => { callbacks.push(callback); return callbacks.length; };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.ResizeObserver = class { constructor(callback: ResizeObserverCallback) { observers.push(() => callback([], this)); } observe() {} disconnect() {} unobserve() {} };
  let finishOldFonts!: () => void;
  const old = document.implementation.createHTMLDocument();
  Object.defineProperty(old, "fonts", { value: { ready: new Promise<void>(resolve => { finishOldFonts = resolve; }) } });
  const current = document.implementation.createHTMLDocument();
  vi.spyOn(current.body, "getBoundingClientRect").mockReturnValue({ height: 420 } as DOMRect);
  let visible = true;
  const flush = () => { while (callbacks.length) callbacks.shift()!(0); };
  const view = render(<OriginalMail message={{ id: "1", direction: "in", from_name: "Buyer", from_email: "buyer@example.test", sent_at: "2026-10-09", body: "Exact words", body_html: "<p>Exact words</p>" }} />);
  try {
    const frame = view.container.querySelector("iframe")!;
    vi.spyOn(frame, "getBoundingClientRect").mockImplementation(() => ({ width: visible ? 400 : 0 } as DOMRect));
    const doc = vi.spyOn(frame, "contentDocument", "get").mockReturnValue(old);
    fireEvent.load(frame); // Old document is still waiting for its fonts.
    doc.mockReturnValue(current);
    fireEvent.load(frame);
    flush();
    expect(frame.style.getPropertyValue("--mail-document-height")).toBe("422px");
    finishOldFonts(); await Promise.resolve(); flush();
    expect(frame.style.getPropertyValue("--mail-document-height")).toBe("422px");
    visible = false; observers.at(-1)!(); flush();
    expect(frame.style.getPropertyValue("--mail-document-height")).toBe("422px");
    visible = true;
    vi.mocked(current.body.getBoundingClientRect).mockReturnValue({ height: 700 } as DOMRect);
    observers.at(-1)!(); flush();
    expect(frame.style.getPropertyValue("--mail-document-height")).toBe("702px");
  } finally {
    view.unmount(); vi.restoreAllMocks();
    globalThis.ResizeObserver = previousObserver;
    globalThis.requestAnimationFrame = previousRaf;
    globalThis.cancelAnimationFrame = previousCancel;
  }
});
