/** 数据来源只有一个接口。现在读 fixtures/;M2 起读 API。界面代码不知道也不该知道区别。
 *  人的动作(确认、忽略、改状态、起草、发信)都要带身份;没有身份的调用服务端会拒绝(宪法第二、五条)。 */

import { replySubject } from "@/lib/text";
import type {
  AttachmentText,
  Lead,
  MailboxInfo,
  OutboxStatus,
  LeadSuggestion,
  LeadStatus,
  Message,
  ReplyDraft,
  SendRequest,
  Thread,
} from "./types";

export interface DataSource {
  threads(): Promise<Thread[]>;
  thread(id: string): Promise<Thread | undefined>;
  suggestions(): Promise<LeadSuggestion[]>;
  failedSuggestions(): Promise<number>;
  leads(): Promise<Lead[]>;
  confirm(suggestionId: string, user: string): Promise<void>;
  dismiss(suggestionId: string, user: string): Promise<void>;
  updateLead(leadId: string, patch: { status?: LeadStatus; next_step?: string }, user: string): Promise<void>;
  /** 这条线程最近一份草稿;没有就是 null */
  latestDraft(threadId: string): Promise<ReplyDraft | null>;
  /** 让模型起一份草稿。模型失败也返回(status: failed)而不是抛——失败要显形(宪法第六条) */
  makeDraft(threadId: string, user: string): Promise<ReplyDraft>;
  /** 以这个人的名义发出。服务端先签一次性令牌再发,两步都要身份(宪法第二条) */
  send(threadId: string, request: SendRequest, user: string): Promise<void>;
  /** 一份附件里读出来的文字(或读不出的原因) */
  attachmentText(attachmentId: string): Promise<AttachmentText>;
  /** 推送给下游的状态 */
  outbox(): Promise<OutboxStatus>;
  /** 伺候的是哪个邮箱、开了哪些任务 */
  mailbox(): Promise<MailboxInfo>;
}

/** 样本附件的文字。真系统里是 pypdf / openpyxl 读出来落库的。 */
const FIXTURE_ATTACHMENTS: Record<string, AttachmentText> = {
  "a-mytel-spec": {
    id: "a-mytel-spec",
    name: "B300-BTO-spec.pdf",
    status: "ok",
    text: [
      "HGX B300 BTO configuration — request for quotation",
      "",
      "Qty\tItem",
      "2\tSYS-A22GA-NBRT (8x NVIDIA B300 SXM)",
      "4\tIntel Xeon 6 6960P",
      "64\t64GB DDR5-6400 ECC RDIMM",
      "16\t7.68TB NVMe U.2 Gen5",
      "2\tNVIDIA ConnectX-8 800G",
      "",
      "Delivery: Yangon, DDP. Target date: 2026-11-15.",
    ].join("\n"),
    reason: "",
  },
  "a-hanbit-po": {
    id: "a-hanbit-po",
    name: "PO-HB-260609.pdf",
    status: "ok",
    text: "PURCHASE ORDER PO-HB-260609\nSupplier: Glocalstorage Pte Ltd\n8 x 4-GPU server (L40S) per quotation Q-2588\nShip to: Hanbit Cloud, Pangyo",
    reason: "",
  },
  "a-lumen-list": {
    id: "a-lumen-list",
    name: "lot-list.jpg",
    status: "failed",
    text: "",
    reason: "图片要走 vision 路由,还没接",
  },
};

/** 样本草稿:照读数编一封,和真模型一样带署名、带核对结果、留 [姓名] 占位。
 *  读数里有对不上的数字,草稿就会照抄——真模型也是这样把幻觉带进回信的,所以告警要一路跟到这里。 */
function fakeDraft(t: Thread): ReplyDraft {
  const base = {
    id: `d-${t.id}`,
    model: "Spark · fast",
    task_version: "draft_reply@3",
    produced_at: new Date().toISOString(),
  };
  const r = t.reading;
  if (!r || r.status !== "ok" || !r.is_inquiry) {
    const reason = r?.status === "failed" ? "读数失败的信不起草:模型看不懂原文" : "不是询盘,没有可回的内容";
    return { ...base, status: "failed", reason };
  }
  const zh = r.language.startsWith("zh");
  const first = t.contact.split(/\s+/)[0] || t.contact;
  const echo = r.unverified.length ? r.unverified[0] : "";
  const body = zh
    ? `${t.contact} 您好,\n\n感谢来信。${echo ? `您提到的 ${echo} 我们已记录。` : ""}我们正在核对库存与交期,尽快给您正式报价。请问交货地址和期望到货时间是?\n\n[姓名]`
    : `Dear ${first},\n\nThank you for your inquiry.${echo ? ` We have noted the ${echo} you mentioned.` : ""} We are checking stock and lead time for the configuration you listed and will revert with a formal quotation shortly.\n\nCould you confirm the delivery address and your target delivery date?\n\nBest regards,\n[姓名]`;
  return {
    ...base,
    status: "ok",
    language: r.language,
    subject: replySubject(t.subject),
    body,
    open_questions: zh ? ["交货地址", "期望到货时间"] : ["delivery address", "target delivery date"],
    quoted_numbers: echo ? [echo] : [],
    unverified: r.unverified,
  };
}

export async function fixtureSource(): Promise<DataSource> {
  const [fxThreads, fx] = await Promise.all([import("../fixtures/threads"), import("../fixtures/leads")]);
  // 样本是只读模块;这里拷一份,让确认/忽略/发信在本页生效
  let threads = [...fxThreads.threads];
  let suggestions = [...fx.suggestions];
  let leads = [...fx.leads];
  const drafts = new Map<string, ReplyDraft>();
  const requirePerson = (user: string, doing: string) => {
    if (!user.trim()) throw new Error(`${doing}要先写上你的名字`);
  };
  const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
  // 列表和 API 一样不带信件与历史;详情才有。界面必须走 thread(id) 才看得到信
  const listEntry = (t: Thread): Thread => ({ ...t, messages: [], history: undefined });
  return {
    threads: async () => threads.map(listEntry),
    thread: async (id) => threads.find((t) => t.id === id),
    suggestions: async () => suggestions,
    failedSuggestions: async () => 0,
    leads: async () => leads,
    confirm: async (id, user) => {
      requirePerson(user, "确认线索");
      const s = suggestions.find((x) => x.id === id);
      if (!s) throw new Error("建议不存在或已处理");
      suggestions = suggestions.filter((x) => x.id !== id);
      leads = [
        {
          id: `l-${s.id}`,
          thread_id: s.thread_id,
          company: s.company,
          contact: s.contact,
          wants: s.wants,
          quantity: s.quantity,
          region: s.region,
          status: "quote",
          confirmed_by: user,
          confirmed_at: new Date().toISOString(),
          next_step: "",
        },
        ...leads,
      ];
    },
    dismiss: async (id, user) => {
      requirePerson(user, "忽略建议");
      suggestions = suggestions.filter((x) => x.id !== id);
    },
    updateLead: async (id, patch, user) => {
      requirePerson(user, "改线索");
      leads = leads.map((l) => (l.id === id ? { ...l, ...patch } : l));
    },
    latestDraft: async (id) => drafts.get(id) ?? null,
    makeDraft: async (id, user) => {
      requirePerson(user, "起草");
      const t = threads.find((x) => x.id === id);
      if (!t) throw new Error("线程不存在");
      await pause(600); // 真模型要几十秒;样本也让「起草中」露个脸
      const draft = fakeDraft(t);
      drafts.set(id, draft);
      return draft;
    },
    send: async (id, request, user) => {
      requirePerson(user, "发信");
      const t = threads.find((x) => x.id === id);
      if (!t) throw new Error("线程不存在");
      const now = new Date().toISOString();
      const out: Message = {
        id: `${id}-out-${t.messages.length + 1}`,
        direction: "out",
        from_name: user,
        from_email: "sales@example.test",
        sent_at: now,
        body: request.body,
      };
      threads = threads.map((x) =>
        x.id === id ? { ...x, folder: "replied", updated_at: now, messages: [...x.messages, out] } : x,
      );
    },
    attachmentText: async (id) => {
      const found = FIXTURE_ATTACHMENTS[id];
      if (!found) throw new Error("没有这个附件");
      return found;
    },
    // 样本里故意留一条没送到的:这个状态得让人看见
    outbox: async () => ({
      configured: true,
      pending: 0,
      failed: 1,
      delivered: 6,
      last_error: "HTTP 503 Service Unavailable(下次 30 分钟后再试)",
    }),
    mailbox: async () => ({
      address: "sales@glocalstorage.example",
      display_name: "Sales",
      tasks: ["read", "leads", "draft"],
    }),
  };
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = ((await response.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

/** 以人的身份发请求。没有 body 就是 POST;带 body 默认 PATCH,可指定 */
const asPerson = (user: string, body?: unknown, method?: "POST" | "PATCH"): RequestInit => ({
  method: method ?? (body === undefined ? "POST" : "PATCH"),
  headers: { "X-User": user, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export function apiSource(): DataSource {
  return {
    threads: () => call<Thread[]>("/api/threads"),
    thread: (id) => call<Thread>(`/api/threads/${id}`),
    suggestions: () => call<LeadSuggestion[]>("/api/leads/suggestions"),
    failedSuggestions: async () => (await call<{ count: number }>("/api/leads/failed")).count,
    leads: () => call<Lead[]>("/api/leads"),
    confirm: async (id, user) => {
      await call(`/api/leads/suggestions/${id}/confirm`, asPerson(user));
    },
    dismiss: async (id, user) => {
      await call(`/api/leads/suggestions/${id}/dismiss`, asPerson(user));
    },
    updateLead: async (id, patch, user) => {
      await call(`/api/leads/${id}`, asPerson(user, patch));
    },
    latestDraft: async (id) => (await call<{ draft: ReplyDraft | null }>(`/api/threads/${id}/draft`)).draft,
    makeDraft: async (id, user) => (await call<{ draft: ReplyDraft }>(`/api/threads/${id}/draft`, asPerson(user))).draft,
    send: async (id, request, user) => {
      // 令牌在按下「发送」的那一刻才签,签给这个人、这条线程,用一次作废
      const { token } = await call<{ token: string }>(`/api/threads/${id}/send-token`, asPerson(user));
      await call(`/api/threads/${id}/send`, asPerson(user, { ...request, token }, "POST"));
    },
    attachmentText: (id) => call<AttachmentText>(`/api/attachments/${id}/text`),
    outbox: () => call<OutboxStatus>("/api/outbox"),
    mailbox: () => call<MailboxInfo>("/api/mailbox"),
  };
}

/** VITE_DATA_SOURCE=api 时走服务端;其余(开发、在线预览)走样本。 */
export function chooseSource(): Promise<DataSource> {
  return import.meta.env.VITE_DATA_SOURCE === "api" ? Promise.resolve(apiSource()) : fixtureSource();
}
