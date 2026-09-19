import { History } from "lucide-react";
import { Link } from "react-router";
import type { HistoryItem } from "@/data/types";
import { shortDate } from "@/lib/text";
import { FOLDER_LABEL, FOLDER_TONE } from "./folders";
import { LEAD_STATUS } from "./lead-table";
import { Pill } from "./pill";
import { Tip } from "./tip";

/** 这位客户此前的往来。代码查出来的事实(ADR-0005):日期、主题、我们记的结果,一行一条,可点回去。 */
export function CustomerHistory({ items }: { items: HistoryItem[] }) {
  const won = items.filter((h) => h.lead_status === "won").length;
  const lost = items.filter((h) => h.lead_status === "lost").length;
  return (
    <section
      aria-label="这位客户"
      data-testid="customer-history"
      className="rounded-lg border border-line bg-surface shadow-sm"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="inline-flex size-6 items-center justify-center rounded-sm bg-surface-3 text-ink-2">
          <History size={14} strokeWidth={2} />
        </span>
        <h3 className="text-sm font-semibold text-ink">这位客户</h3>
        <span className="text-xs text-ink-2">
          此前 <span className="font-mono tabular-nums text-ink">{items.length}</span> 次往来
          {won > 0 && (
            <>
              {" · 成交 "}
              <span className="font-mono tabular-nums text-ok-text">{won}</span>
            </>
          )}
          {lost > 0 && (
            <>
              {" · 丢单 "}
              <span className="font-mono tabular-nums text-ink-2">{lost}</span>
            </>
          )}
        </span>
      </header>
      <ul className="divide-y divide-line">
        {items.map((h) => {
          const lead = h.lead_status ? LEAD_STATUS[h.lead_status] : undefined;
          return (
            <li key={h.id} className="grid grid-cols-row items-center gap-3 px-4 py-2 text-sm">
              <time className="font-mono text-xs tabular-nums text-ink-2" dateTime={h.first_at}>
                {shortDate(h.first_at)}
              </time>
              <Tip label={h.excerpt || h.subject}>
                <Link to={`/t/${h.id}`} className="truncate text-ink hover:text-brand-text hover:underline">
                  {h.subject}
                </Link>
              </Tip>
              <span className="flex items-center gap-1.5">
                {lead ? (
                  <Pill tone={lead.tone} dot>
                    {lead.label}
                  </Pill>
                ) : (
                  <Pill tone={FOLDER_TONE[h.folder]}>{FOLDER_LABEL[h.folder]}</Pill>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
