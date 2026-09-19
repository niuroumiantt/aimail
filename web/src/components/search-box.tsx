import { Search } from "lucide-react";
import { Kbd } from "./kbd";

export function SearchBox({ placeholder = "搜索公司、型号、主题" }: { placeholder?: string }) {
  return (
    <label className="relative block">
      <Search
        size={15}
        strokeWidth={2}
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3"
      />
      <input
        id="search"
        type="search"
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-line bg-canvas pl-8 pr-9 text-sm text-ink placeholder:text-ink-3 focus:border-brand-line focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      />
      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">
        <Kbd>/</Kbd>
      </span>
    </label>
  );
}
