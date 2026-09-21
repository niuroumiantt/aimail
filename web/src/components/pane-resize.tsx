import { useRef, type PointerEvent } from "react";

export function PaneResize({ label, value, min, max, reverse = false, onChange, onReset }: {
  label: string; value: number; min: number; max: number; reverse?: boolean;
  onChange: (width: number) => void; onReset: () => void;
}) {
  const drag = useRef<{ x: number; width: number } | null>(null);
  const clamp = (width: number) => Math.max(min, Math.min(max, width));
  function start(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    const panel = event.currentTarget.parentElement;
    const actual = reverse ? panel?.nextElementSibling?.getBoundingClientRect().width : panel?.getBoundingClientRect().width;
    drag.current = { x: event.clientX, width: actual || value };
  }
  return <div className="ds-pane-resize" role="separator" aria-label={label} aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(value)} tabIndex={0} title="拖动调整宽度；双击恢复；方向键微调" onPointerDown={start} onPointerMove={event => { if (drag.current) onChange(clamp(drag.current.width + (event.clientX - drag.current.x) * (reverse ? -1 : 1))); }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} onDoubleClick={onReset} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); onChange(clamp(value + (event.key === "ArrowRight" ? 12 : -12) * (reverse ? -1 : 1))); } if (event.key === "Home") { event.preventDefault(); onReset(); } }}><span /></div>;
}
