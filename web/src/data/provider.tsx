import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getUser, setUser as persistUser } from "@/lib/user";
import { chooseSource, type DataSource } from "./source";
import type {
  AttachmentText,
  AssistantState,
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
  syncing: boolean;
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
  mailboxes: MailboxInfo[];
  selectMailbox: (address: string) => Promise<void>;
  user: string;
  setUser: (name: string) => void;
  /** 立即收一次信并刷新界面。返回错误文案或空串。 */
  sync: () => Promise<string>;
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
  analyzeThread: (threadId: string) => Promise<string>;
  assistant: () => Promise<AssistantState>;
  askAssistant: (question: string) => Promise<AssistantState>;
  clearAssistant: () => Promise<AssistantState>;
};

const NO_OUTBOX: OutboxStatus = { configured: false, pending: 0, failed: 0, delivered: 0, last_error: "" };

// 还没拿到之前当全开:藏入口是"知道没开"才做的事
const NO_MAILBOX: MailboxInfo = { address: "", display_name: "", tasks: ["read", "leads", "draft"] };

const Ctx = createContext<State | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<DataSource>();
  const activeSource = useRef<DataSource | undefined>(undefined);
  const refreshVersion = useRef(0);
  const pendingDetails = useRef(new Map<string, Promise<void>>());
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string>();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [details, setDetails] = useState<Record<string, Thread>>({});
  const [suggestions, setSuggestions] = useState<LeadSuggestion[]>([]);
  const [failed, setFailed] = useState(0);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [outbox, setOutbox] = useState<OutboxStatus>(NO_OUTBOX);
  const [mailbox, setMailbox] = useState<MailboxInfo>(NO_MAILBOX);
  const [mailboxes, setMailboxes] = useState<MailboxInfo[]>([]);
  const [user, setUserState] = useState(getUser);

  const refresh = useCallback(async (src: DataSource) => {
    if (activeSource.current !== src) return;
    const version = ++refreshVersion.current;
    const current = () => activeSource.current === src && refreshVersion.current === version;
    try {
      // 收件列表先显示；线索和推送状态不能阻挡阅读。
      const [t, m] = await Promise.all([src.threads(), src.mailbox()]);
      if (!current()) return;
      setThreads(t);
      setMailbox(m);
      setLoading(false);
      setError(undefined);
      const [s, f, l, o] = await Promise.all([
        src.suggestions(), src.failedSuggestions(), src.leads(), src.outbox(),
      ]);
      if (!current()) return;
      setSuggestions(s);
      setFailed(f);
      setLeads(l);
      setOutbox(o);
    } catch (e) {
      if (current()) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (current()) setLoading(false);
    }
  }, []);

  const activate = useCallback((src: DataSource, info: MailboxInfo) => {
    activeSource.current = src;
    pendingDetails.current = new Map();
    setSource(src);
    setMailbox(info);
    setLoading(true);
    setSyncing(false);
    setError(undefined);
    setThreads([]);
    setDetails({});
    setSuggestions([]);
    setFailed(0);
    setLeads([]);
    setOutbox(NO_OUTBOX);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const src = await chooseSource();
        if (!alive) return;
        const access = await src.mailboxes();
        const stored = localStorage.getItem("mailbox-address") ?? "";
        const selected = access.items.some(item => item.address === stored) ? stored : access.default;
        if (!alive) return;
        const scoped = src.selectMailbox(selected);
        setMailboxes(access.items);
        activate(scoped, access.items.find(item => item.address === selected) ?? NO_MAILBOX);
        await refresh(scoped);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
        if (alive && !activeSource.current) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      activeSource.current = undefined;
    };
  }, [activate, refresh]);

  const setUser = useCallback((name: string) => {
    persistUser(name);
    setUserState(name.trim());
  }, []);

  const sync = useCallback(async (): Promise<string> => {
    if (!source) return "还没加载完";
    setSyncing(true);
    try {
      await source.sync();
      await refresh(source);
      return "";
    } catch (e) {
      return e instanceof Error ? e.message : String(e);
    } finally {
      if (activeSource.current === source) setSyncing(false);
    }
  }, [source, refresh]);

  const openThread = useCallback(
    async (id: string) => {
      if (!source || activeSource.current !== source) return;
      const pending = pendingDetails.current;
      if (pending.has(id)) return pending.get(id);
      const request = (async () => {
        try {
          const t = await source.thread(id);
          if (t && activeSource.current === source) setDetails((d) => ({ ...d, [id]: t }));
        } catch {
          /* 列表里那份先顶着;下次刷新再试 */
        } finally {
          pending.delete(id);
        }
      })();
      pending.set(id, request);
      return request;
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

  const send = useCallback(
    async (threadId: string, request: SendRequest): Promise<string> => {
      if (!source) return "还没加载完";
      try {
        await source.send(threadId, request, user);
      } catch (e) {
        return e instanceof Error ? e.message : String(e);
      }
      // A successful send must stay successful even when a later refresh is unavailable.
      try {
        await refresh(source);
        await openThread(threadId);
      } catch {
        /* 下一次打开页面会重新拉取；不能诱导用户重复发送。 */
      }
      return "";
    },
    [source, user, refresh, openThread],
  );

  const value = useMemo<State>(
    () => ({
      loading,
      syncing,
      error,
      threads,
      details,
      openThread,
      suggestions,
      failed,
      leads,
      outbox,
      mailbox,
      mailboxes,
      selectMailbox: async (address) => {
        const info = mailboxes.find(item => item.address === address);
        if (!source || !info || address === mailbox.address) return;
        const scoped = source.selectMailbox(address);
        activate(scoped, info);
        await refresh(scoped);
      },
      user,
      setUser,
      sync,
      confirm: (s) => act((src) => src.confirm(s.id, user)),
      dismiss: (s) => act((src) => src.dismiss(s.id, user)),
      updateLead: (id, patch) => act((src) => src.updateLead(id, patch, user)),
      latestDraft: async (id) => (source ? source.latestDraft(id) : null),
      makeDraft: async (id) => {
        if (!source) throw new Error("还没加载完");
        return source.makeDraft(id, user);
      },
      send,
      attachmentText: async (id) => {
        if (!source) throw new Error("还没加载完");
        return source.attachmentText(id);
      },
      analyzeThread: async (id) => {
        if (!source) return "还没加载完";
        try {
          const thread = await source.analyzeThread(id);
          if (activeSource.current === source) setDetails((value) => ({ ...value, [id]: thread }));
          await refresh(source);
          return "";
        } catch (e) {
          return e instanceof Error ? e.message : String(e);
        }
      },
      assistant: async () => {
        if (!source) throw new Error("还没加载完");
        return source.assistant();
      },
      askAssistant: async (question) => {
        if (!source) throw new Error("还没加载完");
        return source.askAssistant(question, user);
      },
      clearAssistant: async () => {
        if (!source) throw new Error("还没加载完");
        return source.clearAssistant(user);
      },
    }),
    [loading, syncing, error, threads, details, openThread, suggestions, failed, leads, outbox, mailbox, mailboxes, user, setUser, sync, act, source, send, refresh, activate],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): State {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData 必须在 DataProvider 里用");
  return v;
}
