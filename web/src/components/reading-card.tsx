import { Ban, CircleAlert, Sparkles, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { Attribution, Reading } from "@/data/types";
import { cn } from "@/lib/cn";
import { fullTime } from "@/lib/text";
import { Pill, type Tone } from "./pill";
import { Tip } from "./tip";
import { Button } from "./button";

/** 署名:谁算的、哪个版本、什么时候。没有署名的读数不渲染——宪法第三条。 */
function Signature({ a }: { a: Attribution }) {
  return (
    <Tip label={`${a.model} · ${a.task_version} · ${fullTime(a.produced_at)}`}>
      <span
        data-testid="attribution"
        className="inline-flex items-center gap-1 whitespace-nowrap font-mono text-2xs text-ink-2"
      >
        {a.model}
        <span className="text-ink-3">·</span>
        {a.task_version}
      </span>
    </Tip>
  );
}

function Frame({
  icon,
  tone,
  title,
  aside,
  children,
  testId,
}: {
  icon: ReactNode;
  tone: Tone;
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  const badge: Record<Tone, string> = {
    neutral: "bg-surface-3 text-ink-2",
    brand: "bg-brand-wash text-brand-text",
    ok: "bg-ok-wash text-ok-text",
    warn: "bg-warn-wash text-warn-text",
    danger: "bg-danger-wash text-danger-text",
  };
  return (
    <section
      data-testid={testId}
      className="rounded-lg border border-line bg-surface shadow-sm"
      aria-label={title}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className={cn("inline-flex size-6 items-center justify-center rounded-sm", badge[tone])}>
          {icon}
        </span>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <span className="ml-auto flex items-center gap-2">{aside}</span>
      </header>
      <div className="grid gap-3 px-4 py-3">{children}</div>
    </section>
  );
}

function Alarm({ numbers }: { numbers: string[] }) {
  return (
    <div
      role="alert"
      data-testid="alarm"
      className="rounded-md border border-warn-line bg-warn-wash px-3 py-2 text-sm text-warn-text"
    >
      <p className="font-semibold">这些数字在原文里找不到,摘要不可信,请以原文为准</p>
      <p className="mt-1 font-mono text-xs">{numbers.join(" · ")}</p>
    </div>
  );
}

const ICON = { size: 14, strokeWidth: 2 } as const;

/** AI 读数卡。四种状态:没有 / 失败 / 不是询盘 / 正常(含数字核对不过的"可疑"态)。 */
export function ReadingCard({ reading, onAnalyze, analyzing = false, error = "" }: { reading?: Reading; onAnalyze?: () => Promise<void>; analyzing?: boolean; error?: string }) {
  if (!reading) {
    return (
      <Frame icon={<Sparkles {...ICON} />} tone="neutral" title="还没有读数" aside={onAnalyze && <Button size="sm" variant="outline" disabled={analyzing} onClick={() => void onAnalyze()}>{analyzing ? "正在阅读…" : "分析这封信"}</Button>} testId="reading-none">
        <p className="text-sm text-ink-2">模型还没处理这封信。</p>
        {error && <p role="alert" className="text-xs text-danger-text">{error}</p>}
      </Frame>
    );
  }

  if (reading.status === "failed") {
    return (
      <Frame
        icon={<Ban {...ICON} />}
        tone="danger"
        title="这封没有读数"
        aside={<Signature a={reading} />}
        testId="reading-failed"
      >
        <p className="text-sm text-ink">模型没有给出合规输出,这封信请直接看原文。</p>
        <p className="font-mono text-xs text-ink-2">{reading.reason}</p>
      </Frame>
    );
  }

  const suspect = reading.unverified.length > 0;
  const tone: Tone = !reading.is_inquiry ? "neutral" : suspect ? "warn" : "brand";
  const icon = !reading.is_inquiry ? (
    <CircleAlert {...ICON} />
  ) : suspect ? (
    <TriangleAlert {...ICON} />
  ) : (
    <Sparkles {...ICON} />
  );

  return (
    <Frame
      icon={icon}
      tone={tone}
      title={reading.is_inquiry ? "AI 读数" : "AI 判断:这不是询盘"}
      aside={
        <>
          <Signature a={reading} />
          <Pill mono>{reading.language}</Pill>
        </>
      }
      testId="reading-ok"
    >
      {suspect && <Alarm numbers={reading.unverified} />}
      {/* 已判定不可信的摘要退到警告后面并调暗:照常排版等于替模型背书 */}
      <div data-testid="summary" data-suspect={suspect || undefined} className={cn(suspect && "opacity-60")}>
        <p className="text-sm leading-relaxed text-ink">{reading.summary_zh}</p>
        <p className="mt-2 text-xs italic leading-relaxed text-ink-2">{reading.summary_en}</p>
        {reading.facts.length > 0 && (
          <ul className="mt-3 grid gap-1.5">
            {reading.facts.map((fact) => (
              <li key={fact} className="flex gap-2 text-sm text-ink">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
                <span>{fact}</span>
              </li>
            ))}
          </ul>
        )}
        {reading.quoted_numbers.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {reading.quoted_numbers.map((n) => (
              <Pill key={n} mono tone={reading.unverified.includes(n) ? "danger" : "neutral"}>
                {n}
              </Pill>
            ))}
          </div>
        )}
      </div>
    </Frame>
  );
}
