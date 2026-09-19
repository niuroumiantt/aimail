import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getUser, setUser as persistUser } from "@/lib/user";
import { chooseSource, type DataSource } from "./source";
import type {
  AttachmentText,
  Lead,
  MailboxInfo,
  OutboxStatus,
  LeadStatus,
  LeadSuggestion,
  ReplyDraft,
  SendRequest,
  Thread,
} from "./types";

type State = {
  loading: boolean;
  error?: string;
  threads: Thread[];
  /** 打开过的线程详情(带信件与客户历史),按 id 存 */
  details: Record<string, Thread>;
  /** 拉一条线程的详情;列表刷新后再调一次就是刷新 */
  openThread: (id: string) => Promise<void>;
  suggestions: LeadSuggestion[];
  failed: number;
  leads: Lead[];
  outbox: OutboxStatus;
  mailbox: MailboxInfo;
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
  /** 附件里读出来的文字,点开才取 */
  attachmentText: (attachmentId: string) => Promise<AttachmentText>;
};

const NO_OUTBOX: OutboxStatus = { configured: false, pending: 0, failed: 0, delivered: 0, last_error: "" };

// 还没拿到之前当全开:藏入口是"知道没开"才做的事
const NO_MAILBOX: MailboxInfo = { address: "", display_name: "", tasks: ["read", "leads", "draft"] };

const Ctx = createContext<State | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<DataSource>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [details, setDetails] = useState<Record<string, Thread>>({});
  const [suggestions, setSuggestions] = useState<LeadSuggestion[]>([]);
  const [failed, setFailed] = useState(0);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [outbox, setOutbox] = useState<OutboxStatus>(NO_OUTBOX);
  const [mailbox, setMailbox] = useState<MailboxInfo>(NO_MAILBOX);
  const [user, setUserState] = useState(getUser);

  const refresh = useCallback(async (src: DataSource) => {
    const [t, s, f, l, o, m] = await Promise.all([
      src.threads(),
      src.suggestions(),
      src.failedSuggestions(),
      src.leads(),
      src.outbox(),
      src.mailbox(),
    ]);
    setThreads(t);
    setSuggestions(s);
    setFailed(f);
    setLeads(l);
    setOutbox(o);
    setMailbox(m);
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

  const openThread = useCallback(
    async (id: string) => {
      if (!source) return;
      try {
        const t = await source.thread(id);
        if (t) setDetails((d) => ({ ...d, [id]: t }));
      } catch {
        /* 列表里那份先顶着;下次刷新再试 */
      }
    },
    [source],
  );

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
      details,
      openThread,
      suggestions,
      failed,
      leads,
      outbox,
      mailbox,
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
      attachmentText: async (id) => {
        if (!source) throw new Error("还没加载完");
        return source.attachmentText(id);
      },
    }),
    [loading, error, threads, details, openThread, suggestions, failed, leads, outbox, mailbox, user, setUser, act, source],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): State {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData 必须在 DataProvider 里用");
  return v;
}
