import { useMemo } from "react";
import { countFolders } from "@/components/folders";
import { AppShell } from "@/components/app-shell";
import { LeadsBoard } from "@/components/leads-board";
import { Sidebar } from "@/components/sidebar";
import { useData } from "@/data/provider";

export default function LeadsPage() {
  const { threads, suggestions, failed, leads, outbox, mailbox, mailboxes, selectMailbox, user, setUser, confirm, dismiss, updateLead, sync, syncing } =
    useData();
  const threadIds = useMemo(() => new Set(threads.map((t) => t.id)), [threads]);
  const counts = useMemo(() => countFolders(threads), [threads]);
  return (
    <AppShell
      title="销售线索"
      sidebar={<Sidebar counts={counts} activeFolder="all" inInbox={false} mailbox={mailbox} mailboxes={mailboxes} onMailboxChange={selectMailbox} onSync={sync} syncing={syncing} />}
      main={
        <LeadsBoard
          suggestions={suggestions}
          failed={failed}
          leads={leads}
          outbox={outbox}
          threadIds={threadIds}
          user={user}
          onSetUser={setUser}
          onConfirm={confirm}
          onDismiss={dismiss}
          onUpdateLead={updateLead}
        />
      }
    />
  );
}
