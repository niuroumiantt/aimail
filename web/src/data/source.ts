/** 数据来源只有一个接口。现在读 fixtures/;M2 起读 API。界面代码不知道也不该知道区别。 */

import type { Lead, LeadSuggestion, Thread } from "./types";

export interface DataSource {
  threads(): Promise<Thread[]>;
  thread(id: string): Promise<Thread | undefined>;
  suggestions(): Promise<LeadSuggestion[]>;
  leads(): Promise<Lead[]>;
}

export async function fixtureSource(): Promise<DataSource> {
  const [{ threads }, { suggestions, leads }] = await Promise.all([
    import("../fixtures/threads"),
    import("../fixtures/leads"),
  ]);
  return {
    threads: async () => threads,
    thread: async (id) => threads.find((t) => t.id === id),
    suggestions: async () => suggestions,
    leads: async () => leads,
  };
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} → ${response.status}`);
  return (await response.json()) as T;
}

export function apiSource(): DataSource {
  return {
    threads: () => get<Thread[]>("/api/threads"),
    thread: (id) => get<Thread>(`/api/threads/${id}`),
    suggestions: () => get<LeadSuggestion[]>("/api/leads/suggestions"),
    leads: () => get<Lead[]>("/api/leads"),
  };
}

/** VITE_DATA_SOURCE=api 时走服务端;其余(开发、在线预览)走样本。 */
export function chooseSource(): Promise<DataSource> {
  return import.meta.env.VITE_DATA_SOURCE === "api" ? Promise.resolve(apiSource()) : fixtureSource();
}
