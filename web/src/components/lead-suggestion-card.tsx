import { Check, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import type { LeadSuggestion, Priority } from "@/data/types";
import { fullTime } from "@/lib/text";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { Card } from "./card";
import { ConfirmDialog } from "./dialog";
import { Pill, type Tone } from "./pill";
import { Tip } from "./tip";

const PRIORITY: Record<Priority, { label: string; tone: Tone }> = {
  high: { label: "优先", tone: "danger" },
  normal: { label: "常规", tone: "neutral" },
  low: { label: "低", tone: "neutral" },
};

/** 模型提的线索建议。人点「确认」之前它不是事实——按钮上就写着。 */
export function LeadSuggestionCard({
  suggestion,
  hasThread,
  onConfirm,
  onDismiss,
}: {
  suggestion: LeadSuggestion;
  hasThread: boolean;
  onConfirm: (s: LeadSuggestion) => void;
  onDismiss: (s: LeadSuggestion) => void;
}) {
  const [asking, setAsking] = useState(false);
  const p = PRIORITY[suggestion.priority];
  return (
    <Card className="grid gap-3 p-4">
      <div className="flex items-start gap-3">
        <Avatar name={suggestion.contact} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-ink">{suggestion.company}</span>
            <Pill tone={p.tone} dot={suggestion.priority === "high"}>
              {p.label}
            </Pill>
          </div>
          <p className="text-xs text-ink-2">
            {suggestion.contact} · {suggestion.region}
          </p>
        </div>
        <Tip label={`${suggestion.model} · ${suggestion.task_version} · ${fullTime(suggestion.produced_at)}`}>
          <span className="font-mono text-2xs text-ink-3">{suggestion.model}</span>
        </Tip>
      </div>

      <dl className="grid grid-cols-kv gap-x-3 gap-y-1 text-sm">
        <dt className="text-ink-2">要什么</dt>
        <dd className="text-ink">{suggestion.wants}</dd>
        <dt className="text-ink-2">多少</dt>
        <dd className="font-mono text-ink">{suggestion.quantity}</dd>
      </dl>

      <div className="flex items-center gap-2">
        <Button variant="solid" size="sm" icon={<Check size={14} strokeWidth={2.25} />} onClick={() => setAsking(true)}>
          确认为线索
        </Button>
        <Button variant="ghost" size="sm" icon={<X size={14} strokeWidth={2} />} onClick={() => onDismiss(suggestion)}>
          忽略
        </Button>
        {hasThread && (
          <Link to={`/t/${suggestion.thread_id}`} className="ml-auto text-xs text-brand-text hover:underline">
            看原信
          </Link>
        )}
      </div>

      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title="确认为线索"
        description="确认后它进入线索表,成为事实;建议本身会消失。这一步只有人能做。"
        confirmLabel="确认"
        onConfirm={() => {
          setAsking(false);
          onConfirm(suggestion);
        }}
      >
        <dl className="grid grid-cols-kv gap-x-3 gap-y-1 rounded-md bg-surface-2 px-3 py-2 text-sm">
          <dt className="text-ink-2">公司</dt>
          <dd className="text-ink">{suggestion.company}</dd>
          <dt className="text-ink-2">要什么</dt>
          <dd className="text-ink">{suggestion.wants}</dd>
          <dt className="text-ink-2">多少</dt>
          <dd className="font-mono text-ink">{suggestion.quantity}</dd>
        </dl>
      </ConfirmDialog>
    </Card>
  );
}
