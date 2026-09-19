import { ChevronDown } from "lucide-react";
import type { LeadStatus } from "@/data/types";
import { cn } from "@/lib/cn";
import { LEAD_STATUS } from "./lead-table";

const TONE_CLASS = {
  neutral: "bg-surface-3 text-ink-2",
  brand: "bg-brand-wash text-brand-deep",
  ok: "bg-ok-wash text-ok-text",
  warn: "bg-warn-wash text-warn-text",
  danger: "bg-danger-wash text-danger-text",
} as const;

/** 线索状态:看着是标签,点开是下拉。原生 select 套一层,键盘和无障碍白得。 */
export function StatusSelect({
  value,
  onChange,
}: {
  value: LeadStatus;
  onChange?: (status: LeadStatus) => void;
}) {
  const s = LEAD_STATUS[value];
  return (
    <label className={cn("relative inline-flex h-5 items-center gap-1 rounded-sm pl-1.5 pr-4 text-2xs font-medium", TONE_CLASS[s.tone])}>
      <span className={cn("size-1.5 rounded-full", { neutral: "bg-ink-3", brand: "bg-brand", ok: "bg-ok", warn: "bg-warn", danger: "bg-danger" }[s.tone])} />
      {s.label}
      <ChevronDown size={10} strokeWidth={2.5} className="absolute right-1" />
      <select
        aria-label="线索状态"
        value={value}
        disabled={!onChange}
        onChange={(e) => onChange?.(e.target.value as LeadStatus)}
        className="absolute inset-0 cursor-pointer opacity-0 disabled:cursor-default"
      >
        {(Object.keys(LEAD_STATUS) as LeadStatus[]).map((k) => (
          <option key={k} value={k}>
            {LEAD_STATUS[k].label}
          </option>
        ))}
      </select>
    </label>
  );
}
