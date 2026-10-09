import { Search } from "lucide-react";
import { Kbd } from "./kbd";
import { useEffect, useRef } from "react";

export function SearchBox({ placeholder = "搜索公司、型号、主题", value, onChange }: { placeholder?: string; value?: string; onChange?: (value: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const focus = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || target?.closest("input, textarea, select, [contenteditable], [role='textbox']")) return;
      event.preventDefault(); input.current?.focus();
    };
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, []);
  return (
    <label className="relative block">
      <Search
        size={15}
        strokeWidth={2}
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3"
      />
      <input
        id="search"
        ref={input}
        aria-label={placeholder}
        type="search"
        placeholder={placeholder}
        value={value}
        onChange={event => onChange?.(event.target.value)}
        className="h-8 w-full rounded-md border border-line bg-canvas pl-8 pr-9 text-sm text-ink placeholder:text-ink-3 focus:border-brand-line focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      />
      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">
        <Kbd>/</Kbd>
      </span>
    </label>
  );
}
