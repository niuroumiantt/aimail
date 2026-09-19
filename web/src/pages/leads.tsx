import { useMemo } from "react";
import { AppShell } from "@/components/app-shell";
import { LeadsBoard } from "@/components/leads-board";
import { Sidebar } from "@/components/sidebar";
import { useData } from "@/data/provider";

export default function LeadsPage() {
  const { threads, suggestions, leads, confirm, dismiss } = useData();
  const threadIds = useMemo(() => new Set(threads.map((t) => t.id)), [threads]);
  const counts = useMemo(() => {
    const c = { all: threads.length, inbox: 0, quote: 0, replied: 0, invalid: 0 };
    for (const t of threads) c[t.folder] += 1;
    return c;
  }, [threads]);
  return (
    <AppShell
      sidebar={<Sidebar counts={counts} activeFolder="all" inInbox={false} />}
      main={
        <LeadsBoard
          suggestions={suggestions}
          leads={leads}
          threadIds={threadIds}
          onConfirm={confirm}
          onDismiss={dismiss}
        />
      }
    />
  );
}
