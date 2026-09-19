import type { Lead, LeadSuggestion } from "@/data/types";
import { EmptyState } from "./empty-state";
import { LeadSuggestionCard } from "./lead-suggestion-card";
import { LeadTable } from "./lead-table";

/** 线索页:上面是模型的建议(等人确认),下面是事实(人确认过的)。两块永远分开。 */
export function LeadsBoard({
  suggestions,
  leads,
  threadIds,
  onConfirm,
  onDismiss,
}: {
  suggestions: LeadSuggestion[];
  leads: Lead[];
  threadIds: Set<string>;
  onConfirm: (s: LeadSuggestion) => void;
  onDismiss: (s: LeadSuggestion) => void;
}) {
  return (
    <div className="mx-auto grid max-w-6xl gap-8 px-6 py-6">
      <section className="grid gap-3">
        <header className="flex items-baseline gap-2">
          <h2 className="text-base font-semibold text-ink">待确认的建议</h2>
          <span className="font-mono text-xs tabular-nums text-ink-2">{suggestions.length}</span>
          <p className="ml-2 text-xs text-ink-2">模型从邮件里提出来的;你确认之前它不算数。</p>
        </header>
        {suggestions.length === 0 ? (
          <EmptyState title="没有待确认的建议" subtitle="新询盘读出来后,线索建议会排在这里等你点头。" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {suggestions.map((s) => (
              <LeadSuggestionCard
                key={s.id}
                suggestion={s}
                hasThread={threadIds.has(s.thread_id)}
                onConfirm={onConfirm}
                onDismiss={onDismiss}
              />
            ))}
          </div>
        )}
      </section>

      <section className="grid gap-3">
        <header className="flex items-baseline gap-2">
          <h2 className="text-base font-semibold text-ink">线索</h2>
          <span className="font-mono text-xs tabular-nums text-ink-2">{leads.length}</span>
          <p className="ml-2 text-xs text-ink-2">人确认过的事实。</p>
        </header>
        <LeadTable leads={leads} threadIds={threadIds} />
      </section>
    </div>
  );
}
