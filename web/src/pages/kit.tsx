import { AppShell } from "@/components/app-shell";
import { Kit } from "@/components/kit";
import { Sidebar } from "@/components/sidebar";
import { useData } from "@/data/provider";

export default function KitPage() {
  const { threads, mailbox, sync, syncing } = useData();
  const counts = { all: threads.length, inbox: 0, quote: 0, replied: 0, invalid: 0 };
  for (const t of threads) counts[t.folder] += 1;
  return (
    <AppShell
      sidebar={<Sidebar counts={counts} activeFolder="all" inInbox={false} mailbox={mailbox} onSync={sync} syncing={syncing} />}
      main={<Kit />}
    />
  );
}
