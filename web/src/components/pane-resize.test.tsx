import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PaneResize } from "./pane-resize";

afterEach(() => vi.unstubAllGlobals());

it("measures a customer pane's start edge and lets the reader grow when the divider moves right", () => {
  vi.stubGlobal("PointerEvent", MouseEvent);
  const changed = vi.fn();
  const view = render(<div><aside><PaneResize label="Customer boundary" value={320} min={280} max={520} reverse edge="start" onChange={changed} onReset={() => {}} /></aside><div /></div>);
  const panel = view.container.querySelector("aside")!;
  panel.getBoundingClientRect = vi.fn(() => ({ width: 330 }) as DOMRect);
  panel.nextElementSibling!.getBoundingClientRect = vi.fn(() => ({ width: 999 }) as DOMRect);
  const handle = screen.getByRole("separator", { name: "Customer boundary" });
  Object.defineProperty(handle, "setPointerCapture", { value: vi.fn() });
  fireEvent.pointerDown(handle, { button: 0, clientX: 800 });
  expect(handle).toHaveAttribute("data-dragging", "true");
  expect(document.documentElement).toHaveAttribute("data-pane-resizing", "true");
  fireEvent.pointerMove(handle, { clientX: 830 });
  expect(changed).toHaveBeenLastCalledWith(300);
  fireEvent.pointerUp(handle);
  expect(handle).toHaveAttribute("data-dragging", "false");
  expect(document.documentElement).not.toHaveAttribute("data-pane-resizing");
  changed.mockClear();
  fireEvent.pointerMove(handle, { clientX: 850 });
  expect(changed).not.toHaveBeenCalled();
});

it("retains the existing reverse handle contract for adjacent assistant panes", () => {
  vi.stubGlobal("PointerEvent", MouseEvent);
  const changed = vi.fn();
  const view = render(<div><main><PaneResize label="Assistant boundary" value={320} min={280} max={520} reverse onChange={changed} onReset={() => {}} /></main><aside /></div>);
  view.container.querySelector("main")!.getBoundingClientRect = vi.fn(() => ({ width: 999 }) as DOMRect);
  view.container.querySelector("aside")!.getBoundingClientRect = vi.fn(() => ({ width: 340 }) as DOMRect);
  const handle = screen.getByRole("separator", { name: "Assistant boundary" });
  Object.defineProperty(handle, "setPointerCapture", { value: vi.fn() });
  fireEvent.pointerDown(handle, { button: 0, clientX: 800 });
  fireEvent.pointerMove(handle, { clientX: 830 });
  expect(changed).toHaveBeenLastCalledWith(310);
  fireEvent.lostPointerCapture(handle);
  expect(handle).toHaveAttribute("data-dragging", "false");
  expect(document.documentElement).not.toHaveAttribute("data-pane-resizing");
});

it("restores the document interaction state when a dragged pane is removed", () => {
  vi.stubGlobal("PointerEvent", MouseEvent);
  const view = render(<div><PaneResize label="Removed pane" value={360} min={260} max={600} onChange={() => {}} onReset={() => {}} /></div>);
  const handle = screen.getByRole("separator");
  Object.defineProperty(handle, "setPointerCapture", { value: vi.fn() });
  fireEvent.pointerDown(handle, { button: 0, clientX: 400 });
  expect(document.documentElement).toHaveAttribute("data-pane-resizing", "true");
  view.unmount();
  expect(document.documentElement).not.toHaveAttribute("data-pane-resizing");
});
