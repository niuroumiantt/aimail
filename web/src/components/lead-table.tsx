import { Link } from "react-router";
import type { Lead, LeadStatus } from "@/data/types";
import { relativeTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { Pill, type Tone } from "./pill";

export const LEAD_STATUS: Record<LeadStatus, { label: string; tone: Tone }> = {
  quote: { label: "待报价", tone: "warn" },
  quoted: { label: "已报价", tone: "brand" },
  following: { label: "跟进中", tone: "brand" },
  won: { label: "成交", tone: "ok" },
  lost: { label: "丢单", tone: "neutral" },
};

export function LeadTable({ leads, threadIds }: { leads: Lead[]; threadIds: Set<string> }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface shadow-sm">
      <table className="w-full min-w-160 border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left text-2xs font-medium uppercase tracking-wider text-ink-3">
            <th className="px-4 py-2.5 font-medium">公司</th>
            <th className="px-3 py-2.5 font-medium">要什么</th>
            <th className="px-3 py-2.5 font-medium">多少</th>
            <th className="px-3 py-2.5 font-medium">状态</th>
            <th className="px-3 py-2.5 font-medium">下一步</th>
            <th className="px-4 py-2.5 text-right font-medium">确认</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => {
            const s = LEAD_STATUS[lead.status];
            return (
              <tr key={lead.id} className="border-b border-line last:border-b-0 hover:bg-surface-2">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <Avatar name={lead.contact} size="sm" muted={lead.status === "lost"} />
                    <div className="min-w-0">
                      <div className="font-medium text-ink">
                        {threadIds.has(lead.thread_id) ? (
                          <Link to={`/t/${lead.thread_id}`} className="hover:text-brand-text hover:underline">
                            {lead.company}
                          </Link>
                        ) : (
                          lead.company
                        )}
                      </div>
                      <div className="text-xs text-ink-2">
                        {lead.contact} · {lead.region}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-3 text-ink">{lead.wants}</td>
                <td className="whitespace-nowrap px-3 py-3 font-mono text-ink">{lead.quantity}</td>
                <td className="px-3 py-3">
                  <Pill tone={s.tone} dot>
                    {s.label}
                  </Pill>
                </td>
                <td className="max-w-xs px-3 py-3 text-ink-2">{lead.next_step}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right text-xs text-ink-2">
                  {lead.confirmed_by}
                  <span className="text-ink-3"> · </span>
                  <time dateTime={lead.confirmed_at}>{relativeTime(lead.confirmed_at)}</time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
