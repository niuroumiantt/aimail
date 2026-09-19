import { Check, Reply } from "lucide-react";
import type { ReactNode } from "react";
import type { HistoryItem, Reading, ReplyDraft, Thread } from "@/data/types";
import { Avatar } from "./avatar";
import { Button } from "./button";
import { Card } from "./card";
import { CustomerHistory } from "./customer-history";
import { EmptyState } from "./empty-state";
import { Kbd } from "./kbd";
import { LEAD_STATUS } from "./lead-table";
import { Pill, type Tone } from "./pill";
import { ReadingCard } from "./reading-card";
import { ReplyComposer, type ReplyHandlers } from "./reply-composer";
import { SearchBox } from "./search-box";

const SWATCHES: Array<[string, string]> = [
  ["canvas", "bg-canvas"],
  ["surface", "bg-surface"],
  ["surface-2", "bg-surface-2"],
  ["surface-3", "bg-surface-3"],
  ["line", "bg-line"],
  ["line-2", "bg-line-2"],
  ["ink-3", "bg-ink-3"],
  ["ink-2", "bg-ink-2"],
  ["ink", "bg-ink"],
  ["brand-wash", "bg-brand-wash"],
  ["brand-wash-2", "bg-brand-wash-2"],
  ["brand-line", "bg-brand-line"],
  ["brand", "bg-brand"],
  ["brand-2", "bg-brand-2"],
  ["brand-text", "bg-brand-text"],
  ["brand-deep", "bg-brand-deep"],
  ["ok-wash", "bg-ok-wash"],
  ["ok", "bg-ok"],
  ["ok-text", "bg-ok-text"],
  ["warn-wash", "bg-warn-wash"],
  ["warn", "bg-warn"],
  ["warn-text", "bg-warn-text"],
  ["danger-wash", "bg-danger-wash"],
  ["danger", "bg-danger"],
  ["danger-text", "bg-danger-text"],
];

const TONES: Tone[] = ["neutral", "brand", "ok", "warn", "danger"];

const base = { model: "Spark · fast", task_version: "summarize_inquiry@3", produced_at: "2026-09-19T08:13:41+08:00" };
const KIT_THREAD: Thread = {
  id: "kit",
  subject: "RFQ – 48 × 2U servers",
  company: "Aurora Compute Oy",
  contact: "Mikko Laine",
  email: "mikko.laine@auroracompute.example",
  region: "赫尔辛基",
  scale: "48 台 · 2U",
  folder: "inbox",
  updated_at: "2026-09-19T08:12:00+08:00",
  messages: [],
};
const KIT_DRAFT: ReplyDraft = {
  ...base,
  id: "kit-draft",
  task_version: "draft_reply@3",
  status: "ok",
  language: "en",
  subject: "Re: RFQ – 48 × 2U servers",
  body: "Dear Mikko,\n\nThank you for your inquiry for 480 units. We are checking stock and lead time and will revert with a quotation shortly.\n\nBest regards,\n[姓名]",
  open_questions: ["delivery address"],
  quoted_numbers: ["480"],
  unverified: ["480"],
};
/** 样品间里的回信框:起草给一份带幻觉数字的草稿,发送永远被服务端拒——只看样子,不出门。 */
const KIT_REPLY: ReplyHandlers = {
  user: "Larry",
  onSetUser: () => {},
  latestDraft: async () => null,
  makeDraft: async () => KIT_DRAFT,
  send: async () => "样品间里发不出去",
};

const KIT_HISTORY: HistoryItem[] = [
  {
    id: "kit-1",
    subject: "RFQ: 4-GPU L40S servers for AI lab",
    first_at: "2026-06-02T11:00:00+08:00",
    last_at: "2026-06-09T15:20:00+08:00",
    folder: "replied",
    replied: true,
    lead_status: "won",
    excerpt: "PO attached, please proceed.",
  },
  {
    id: "kit-2",
    subject: "Spare PSUs for the R740 fleet",
    first_at: "2026-03-14T09:30:00+08:00",
    last_at: "2026-03-20T18:00:00+08:00",
    folder: "replied",
    replied: true,
    lead_status: "lost",
    excerpt: "We went with a local supplier this time.",
  },
  {
    id: "kit-3",
    subject: "Question about warranty terms",
    first_at: "2026-01-08T10:00:00+08:00",
    last_at: "2026-01-08T10:00:00+08:00",
    folder: "invalid",
    replied: false,
    lead_status: "",
    excerpt: "Do refurbished units carry the same warranty?",
  },
];

const READINGS: Array<[string, Reading | undefined]> = [
  [
    "正常",
    {
      ...base,
      status: "ok",
      is_inquiry: true,
      language: "en",
      summary_zh: "客户要 48 台 2U 服务器,CIF 赫尔辛基,12 个月保修。",
      summary_en: "Customer needs 48 × 2U servers, CIF Helsinki, 12-month warranty.",
      facts: ["48 台 2U", "CIF 赫尔辛基", "12 个月保修"],
      quoted_numbers: ["48", "2U", "12"],
      unverified: [],
    },
  ],
  [
    "数字可疑",
    {
      ...base,
      status: "ok",
      is_inquiry: true,
      language: "en",
      summary_zh: "客户要 1,200 条内存,目标价 125 美元。",
      summary_en: "Customer needs 1,200 modules at USD 125 target.",
      facts: ["目标价 125 美元"],
      quoted_numbers: ["1200", "125"],
      unverified: ["1200"],
    },
  ],
  [
    "不是询盘",
    {
      ...base,
      status: "ok",
      is_inquiry: false,
      language: "en",
      summary_zh: "这是丢单通知,不是询盘。",
      summary_en: "A lost-deal notice, not an inquiry.",
      facts: ["输在交期"],
      quoted_numbers: [],
      unverified: [],
    },
  ],
  ["失败", { ...base, status: "failed", reason: "两次都没给出合规 JSON" }],
  ["还没有", undefined],
];

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <header className="flex items-baseline gap-2">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {note && <p className="text-xs text-ink-2">{note}</p>}
      </header>
      {children}
    </section>
  );
}

/** 组件页:每个组件的每种状态都在这儿,亮暗两套一起看。代替 Storybook。 */
export function Kit() {
  return (
    <div className="mx-auto grid max-w-5xl gap-10 px-6 py-6">
      <Section title="色板" note="sage 中性 + teal 品牌 + 三个语义色。全部来自 tokens/theme.css,别处不许写色值。">
        <div className="grid grid-cols-5 gap-2 md:grid-cols-9">
          {SWATCHES.map(([name, cls]) => (
            <div key={name} className="grid gap-1">
              <div className={`h-10 rounded-md border border-line ${cls}`} />
              <span className="font-mono text-2xs text-ink-2">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="字" note="IBM Plex Sans 正文,Plex Mono 给型号与数字;中文落到系统苹方。">
        <Card className="grid gap-2 p-4">
          <p className="text-2xl font-semibold tracking-tight text-ink">询盘工作台 Inquiry desk</p>
          <p className="text-base text-ink">Aurora Compute 要 48 台 2U 服务器,CIF 赫尔辛基。</p>
          <p className="text-sm text-ink">Body 14 — 业务员一天看几十封,这一档要最舒服。</p>
          <p className="text-xs text-ink-2">Meta 12 — 时间、邮箱、地区。</p>
          <p className="font-mono text-sm text-ink">SYS-6029U-TR4 · E5-2680v4 · 3.84TB · USD 4,850</p>
          <p className="text-2xs uppercase tracking-wider text-ink-3">Label 11 · 分组标题</p>
        </Card>
      </Section>

      <Section title="按钮">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="solid" icon={<Check size={14} strokeWidth={2.25} />}>确认为线索</Button>
          <Button variant="soft">软</Button>
          <Button>描边</Button>
          <Button variant="ghost">幽灵</Button>
          <Button variant="danger">删除</Button>
          <Button disabled icon={<Reply size={14} />}>禁用</Button>
          <Button size="sm" variant="solid">小</Button>
          <Button size="sm">小描边</Button>
          <Button size="sm" variant="ghost" aria-label="仅图标" icon={<Reply size={15} strokeWidth={1.75} />} />
        </div>
      </Section>

      <Section title="标签">
        <div className="flex flex-wrap items-center gap-2">
          {TONES.map((t) => (
            <Pill key={t} tone={t} dot>
              {t}
            </Pill>
          ))}
          <Pill mono>SYS-821GE-TNHR</Pill>
          <Pill mono tone="danger">1200</Pill>
          {Object.values(LEAD_STATUS).map((s) => (
            <Pill key={s.label} tone={s.tone} dot>
              {s.label}
            </Pill>
          ))}
        </div>
      </Section>

      <Section title="头像" note="同一个名字永远同一个色;圆角随尺寸走。">
        <div className="flex flex-wrap items-center gap-3">
          {["Mikko Laine", "王婷", "Omar Haddad", "김민준", "Ana Ribeiro", "Nguyễn Thị Lan"].map((n) => (
            <Avatar key={n} name={n} size="lg" />
          ))}
          <Avatar name="Mikko Laine" size="md" />
          <Avatar name="Mikko Laine" size="sm" />
          <Avatar name="Priya Nair" size="md" muted />
        </div>
      </Section>

      <Section title="输入与键位">
        <div className="grid max-w-sm gap-3">
          <SearchBox />
          <p className="flex items-center gap-1.5 text-sm text-ink-2">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> 移动 <Kbd>Enter</Kbd> 打开 <Kbd>/</Kbd> 搜索
          </p>
        </div>
      </Section>

      <Section title="读数卡" note="四种状态;不可信的摘要被压在警告下面并调暗。">
        <div className="grid gap-4 lg:grid-cols-2">
          {READINGS.map(([label, r]) => (
            <div key={label} className="grid gap-1.5">
              <span className="text-2xs uppercase tracking-wider text-ink-3">{label}</span>
              <ReadingCard reading={r} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="这位客户" note="代码从不可变记录里查出来的往来(ADR-0005):日期、主题、我们记的结果;没有往来的线程在页头标「第一次来信」。">
        <div className="max-w-3xl">
          <CustomerHistory items={KIT_HISTORY} />
        </div>
      </Section>

      <Section title="回信框" note="模型只起草;改和发都是人。署名、对不上的数字、追问、占位提醒都压在正文上面。">
        <div className="max-w-3xl">
          <ReplyComposer thread={KIT_THREAD} reply={KIT_REPLY} onClose={() => {}} />
        </div>
      </Section>

      <Section title="空状态">
        <Card className="h-72 overflow-hidden">
          <EmptyState
            title="这个分组是空的"
            subtitle="新来的询盘会按读数结果自动落到对应分组。"
            action={<Button variant="soft">看全部</Button>}
          />
        </Card>
      </Section>
    </div>
  );
}
