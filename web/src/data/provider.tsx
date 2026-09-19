import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { chooseSource } from "./source";
import type { Lead, LeadSuggestion, Thread } from "./types";

type State = {
  loading: boolean;
  error?: string;
  threads: Thread[];
  suggestions: LeadSuggestion[];
  leads: Lead[];
  /** 人确认一条建议 → 变成线索。M4 起走 API;现在只在本页生效。 */
  confirm: (s: LeadSuggestion) => void;
  dismiss: (s: LeadSuggestion) => void;
};

const Ctx = createContext<State | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [suggestions, setSuggestions] = useState<LeadSuggestion[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const source = await chooseSource();
        const [t, s, l] = await Promise.all([source.threads(), source.suggestions(), source.leads()]);
        if (!alive) return;
        setThreads(t);
        setSuggestions(s);
        setLeads(l);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const confirm = useCallback((s: LeadSuggestion) => {
    setSuggestions((prev) => prev.filter((x) => x.id !== s.id));
    setLeads((prev) => [
      {
        id: `l-${s.id}`,
        thread_id: s.thread_id,
        company: s.company,
        contact: s.contact,
        wants: s.wants,
        quantity: s.quantity,
        region: s.region,
        status: "quote",
        confirmed_by: "你",
        confirmed_at: new Date().toISOString(),
        next_step: "报价",
      },
      ...prev,
    ]);
  }, []);

  const dismiss = useCallback((s: LeadSuggestion) => {
    setSuggestions((prev) => prev.filter((x) => x.id !== s.id));
  }, []);

  const value = useMemo(
    () => ({ loading, error, threads, suggestions, leads, confirm, dismiss }),
    [loading, error, threads, suggestions, leads, confirm, dismiss],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): State {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData 必须在 DataProvider 里用");
  return v;
}
