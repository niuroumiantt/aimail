import { useEffect, useRef, useState, type PointerEvent } from "react";

export function PaneResize({ label, value, min, max, reverse = false, edge = "end", onChange, onReset }: {
  label: string; value: number; min: number; max: number; reverse?: boolean; edge?: "start" | "end";
  onChange: (width: number) => void; onReset: () => void;
}) {
  const drag = useRef<{ x: number; width: number; pointerId: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    if (!dragging) return;
    const root = document.documentElement;
    const previous = root.getAttribute("data-pane-resizing");
    root.setAttribute("data-pane-resizing", "true");
    return () => {
      if (previous === null) root.removeAttribute("data-pane-resizing");
      else root.setAttribute("data-pane-resizing", previous);
    };
  }, [dragging]);
  const clamp = (width: number) => Math.max(min, Math.min(max, width));
  function finish(event: PointerEvent<HTMLDivElement>) {
    if (drag.current && event.pointerId !== drag.current.pointerId) return;
    drag.current = null;
    setDragging(false);
  }
  function start(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || drag.current) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    const panel = event.currentTarget.parentElement;
    const actual = reverse && edge === "end" ? panel?.nextElementSibling?.getBoundingClientRect().width : panel?.getBoundingClientRect().width;
    drag.current = { x: event.clientX, width: actual || value, pointerId: event.pointerId };
    setDragging(true);
  }
  return <div className="ds-pane-resize" data-edge={edge} data-dragging={dragging} role="separator" aria-label={label} aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(value)} tabIndex={0} title="整条分隔区域均可拖动；双击恢复；方向键微调" onPointerDown={start} onPointerMove={event => { if (drag.current && event.pointerId === drag.current.pointerId) onChange(clamp(drag.current.width + (event.clientX - drag.current.x) * (reverse ? -1 : 1))); }} onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish} onDoubleClick={onReset} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); onChange(clamp(value + (event.key === "ArrowRight" ? 12 : -12) * (reverse ? -1 : 1))); } if (event.key === "Home") { event.preventDefault(); event.stopPropagation(); onReset(); } }}><span /></div>;
}
