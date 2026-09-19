/** 数据来源只有一个接口。现在读 fixtures/;M2 起读 API。界面代码不知道也不该知道区别。
 *  人的动作(确认、忽略、改状态)都要带身份;没有身份的调用服务端会拒绝(宪法第五条)。 */

import type { Lead, LeadSuggestion, LeadStatus, Thread } from "./types";

export interface DataSource {
  threads(): Promise<Thread[]>;
  thread(id: string): Promise<Thread | undefined>;
  suggestions(): Promise<LeadSuggestion[]>;
  failedSuggestions(): Promise<number>;
  leads(): Promise<Lead[]>;
  confirm(suggestionId: string, user: string): Promise<void>;
  dismiss(suggestionId: string, user: string): Promise<void>;
  updateLead(leadId: string, patch: { status?: LeadStatus; next_step?: string }, user: string): Promise<void>;
}

export async function fixtureSource(): Promise<DataSource> {
  const [{ threads }, fx] = await Promise.all([import("../fixtures/threads"), import("../fixtures/leads")]);
  // 样本是只读模块;这里拷一份,让确认/忽略在本页生效
  let suggestions = [...fx.suggestions];
  let leads = [...fx.leads];
  const requirePerson = (user: string) => {
    if (!user.trim()) throw new Error("确认线索要先写上你的名字");
  };
  return {
    threads: async () => threads,
    thread: async (id) => threads.find((t) => t.id === id),
    suggestions: async () => suggestions,
    failedSuggestions: async () => 0,
    leads: async () => leads,
    confirm: async (id, user) => {
      requirePerson(user);
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
      requirePerson(user);
      suggestions = suggestions.filter((x) => x.id !== id);
    },
    updateLead: async (id, patch, user) => {
      requirePerson(user);
      leads = leads.map((l) => (l.id === id ? { ...l, ...patch } : l));
    },
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

const asPerson = (user: string, body?: unknown): RequestInit => ({
  method: body === undefined ? "POST" : "PATCH",
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
  };
}

/** VITE_DATA_SOURCE=api 时走服务端;其余(开发、在线预览)走样本。 */
export function chooseSource(): Promise<DataSource> {
  return import.meta.env.VITE_DATA_SOURCE === "api" ? Promise.resolve(apiSource()) : fixtureSource();
}
