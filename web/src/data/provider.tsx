import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getUser, setUser as persistUser } from "@/lib/user";
import { chooseSource, type DataSource } from "./source";
import type { Lead, LeadStatus, LeadSuggestion, ReplyDraft, SendRequest, Thread } from "./types";

type State = {
  loading: boolean;
  error?: string;
  threads: Thread[];
  suggestions: LeadSuggestion[];
  failed: number;
  leads: Lead[];
  user: string;
  setUser: (name: string) => void;
  /** 人确认一条建议 → 变成线索。没有名字会被拒(宪法第五条)。返回错误文案或空串 */
  confirm: (s: LeadSuggestion) => Promise<string>;
  dismiss: (s: LeadSuggestion) => Promise<string>;
  updateLead: (id: string, patch: { status?: LeadStatus; next_step?: string }) => Promise<string>;
  /** 这条线程最近一份草稿 */
  latestDraft: (threadId: string) => Promise<ReplyDraft | null>;
  /** 让模型起草。模型失败返回 status: failed;没名字、没加载完才抛 */
  makeDraft: (threadId: string) => Promise<ReplyDraft>;
  /** 以当前这个人的名义发出。返回错误文案或空串;成功后线程列表刷新 */
  send: (threadId: string, request: SendRequest) => Promise<string>;
};

const Ctx = createContext<State | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<DataSource>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [suggestions, setSuggestions] = useState<LeadSuggestion[]>([]);
  const [failed, setFailed] = useState(0);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [user, setUserState] = useState(getUser);

  const refresh = useCallback(async (src: DataSource) => {
    const [t, s, f, l] = await Promise.all([src.threads(), src.suggestions(), src.failedSuggestions(), src.leads()]);
    setThreads(t);
    setSuggestions(s);
    setFailed(f);
    setLeads(l);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const src = await chooseSource();
        if (!alive) return;
        setSource(src);
        await refresh(src);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [refresh]);

  const setUser = useCallback((name: string) => {
    persistUser(name);
    setUserState(name.trim());
  }, []);

  const act = useCallback(
    async (fn: (src: DataSource) => Promise<void>): Promise<string> => {
      if (!source) return "还没加载完";
      try {
        await fn(source);
        await refresh(source);
        return "";
      } catch (e) {
        return e instanceof Error ? e.message : String(e);
      }
    },
    [source, refresh],
  );

  const value = useMemo<State>(
    () => ({
      loading,
      error,
      threads,
      suggestions,
      failed,
      leads,
      user,
      setUser,
      confirm: (s) => act((src) => src.confirm(s.id, user)),
      dismiss: (s) => act((src) => src.dismiss(s.id, user)),
      updateLead: (id, patch) => act((src) => src.updateLead(id, patch, user)),
      latestDraft: async (id) => (source ? source.latestDraft(id) : null),
      makeDraft: async (id) => {
        if (!source) throw new Error("还没加载完");
        return source.makeDraft(id, user);
      },
      send: (id, request) => act((src) => src.send(id, request, user)),
    }),
    [loading, error, threads, suggestions, failed, leads, user, setUser, act, source],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): State {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData 必须在 DataProvider 里用");
  return v;
}
